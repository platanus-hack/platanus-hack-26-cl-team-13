"""sandbox-host: API HTTP sobre el provider local, para correr las cajas en otra máquina.

Corre en la VM de cajas (gemelo-sbx), en el host y no en un contenedor: el provider usa
el CLI de Docker y el admin del proxy en 127.0.0.1:3129. La usa `RemoteProvider`.

    AIGIS_SANDBOX_HOST_TOKEN=... uvicorn aigis.sandbox_host:app --host 100.100.0.8 --port 8080

Reglas:
- Bearer obligatorio (AIGIS_SANDBOX_HOST_TOKEN). Sin token configurado no arranca.
- Solo opera sobre cajas `aigis.*`; la imagen, el runtime y los límites salen de la
  configuración de esta máquina, no del request.
- `exec` corre siempre dentro de una caja. Si el cliente corta, el provider mata el proceso.
- Reaper propio cada 60 s: si el orquestador cae, las cajas igual vencen por TTL.
- Tope de cajas vivas (AIGIS_SANDBOX_HOST_MAX_BOXES): 429 al pasarse.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .providers import Sandbox
from .providers.local import LocalProvider
from .providers.remote import net_from_dict, sb_to_dict, spec_from_dict

TOKEN = os.environ.get("AIGIS_SANDBOX_HOST_TOKEN", "")
MAX_BOXES = int(os.environ.get("AIGIS_SANDBOX_HOST_MAX_BOXES", "10"))


class ExecBody(BaseModel):
    cmd: list[str]
    env: dict[str, str] = {}
    user: str = "agent"
    cwd: str = "/workspace"
    timeout: float | None = None


class FilesBody(BaseModel):
    files: dict[str, str]  # ruta absoluta -> base64
    mode: int = 0o644
    owner: str = "agent"


def create_app(provider: LocalProvider | None = None) -> FastAPI:
    if not TOKEN and provider is None:
        raise RuntimeError("AIGIS_SANDBOX_HOST_TOKEN vacío: sandbox-host no arranca sin token")
    state: dict = {"prov": provider} if provider is not None else {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        prov = state.get("prov") or LocalProvider()
        ensure = getattr(prov, "ensure_infra", None)
        if ensure:
            await ensure()
        state["prov"] = prov

        async def reaper():
            while True:
                await asyncio.sleep(60)
                try:
                    reap = getattr(prov, "reap", None)
                    n = await reap() if reap else 0
                    if n:
                        print(f"reaper: {n} cajas vencidas", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"reaper: {type(e).__name__}: {e}", flush=True)

        task = asyncio.create_task(reaper())
        yield
        task.cancel()

    app = FastAPI(title="Gemelo sandbox-host", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def auth(authorization: str = Header(default="")) -> None:
        if not TOKEN or not hmac.compare_digest(authorization.removeprefix("Bearer ").strip(), TOKEN):
            raise HTTPException(401)

    def prov() -> LocalProvider:
        return state["prov"]

    async def box(sid: str) -> Sandbox:
        p = prov()
        sb = getattr(p, "boxes", {}).get(sid)
        if sb is None:
            sb = next((x for x in await p.list() if x.id == sid), None)
        if sb is None:
            raise HTTPException(404, "no existe esa caja")
        return sb

    @app.get("/health", dependencies=[Depends(auth)])
    async def health():
        boxes = await prov().list()
        return {"ok": True, "boxes": len(boxes), "max_boxes": MAX_BOXES,
                "provider": prov().name, "runtime": getattr(prov(), "runtime", None) or "runc"}

    @app.post("/sandboxes", dependencies=[Depends(auth)])
    async def create(body: dict):
        if len(await prov().list()) >= MAX_BOXES:
            raise HTTPException(429, f"tope de {MAX_BOXES} cajas vivas")
        spec = spec_from_dict(body)
        spec.template = ""  # la imagen la decide esta máquina
        return sb_to_dict(await prov().create(spec))

    @app.put("/sandboxes/{sid}/network", dependencies=[Depends(auth)])
    async def set_network(sid: str, body: dict):
        await prov().set_network(await box(sid), net_from_dict(body))
        return {"ok": True}

    @app.post("/sandboxes/{sid}/files", dependencies=[Depends(auth)])
    async def write_files(sid: str, body: FilesBody):
        files = {p: base64.b64decode(v) for p, v in body.files.items()}
        if any(not p.startswith("/") or ".." in p.split("/") for p in files):
            raise HTTPException(422, "rutas absolutas y sin ..")
        await prov().write_files(await box(sid), files, mode=body.mode, owner=body.owner)
        return {"ok": True}

    @app.get("/sandboxes/{sid}/file", dependencies=[Depends(auth)])
    async def read_file(sid: str, path: str):
        try:
            data = await prov().read_file(await box(sid), path)
        except RuntimeError as e:
            raise HTTPException(404, str(e)[:300]) from e
        return Response(data, media_type="application/octet-stream")

    @app.get("/sandboxes/{sid}/dir", dependencies=[Depends(auth)])
    async def list_dir(sid: str, path: str):
        return await prov().list_dir(await box(sid), path)

    @app.post("/sandboxes/{sid}/exec", dependencies=[Depends(auth)])
    async def exec_(sid: str, body: ExecBody):
        sb = await box(sid)

        async def gen():
            try:
                async for ev in prov().exec(sb, body.cmd, env=body.env, user=body.user, cwd=body.cwd,
                                            timeout=body.timeout):
                    yield json.dumps({"stream": ev.stream, "data": ev.data}) + "\n"
            except (TimeoutError, asyncio.TimeoutError):
                yield json.dumps({"stream": "error", "data": "timeout"}) + "\n"
            except Exception as e:  # noqa: BLE001
                yield json.dumps({"stream": "error", "data": f"{type(e).__name__}: {e}"[:500]}) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.delete("/sandboxes/{sid}", dependencies=[Depends(auth)])
    async def destroy(sid: str):
        await prov().destroy(await box(sid))
        return {"ok": True}

    @app.get("/sandboxes", dependencies=[Depends(auth)])
    async def list_(run_id: str | None = None):
        return [sb_to_dict(sb) for sb in await prov().list(run_id)]

    return app


app = create_app() if TOKEN else None
