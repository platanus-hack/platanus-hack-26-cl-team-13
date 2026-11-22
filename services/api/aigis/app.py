"""API HTTP del orquestador.

Correr en local:
    cd services/api && .venv/Scripts/python -m uvicorn aigis.app:app --port 8000
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from .config import Settings, get_settings
from .gateway_client import GatewayClient, HttpGateway, StubGateway
from .lanes.catalog import CATALOG
from .models import RunRequest
from .providers import SandboxProvider, get_provider
from .runner import Orchestrator
from .store import MemoryStore, Store


def create_app(
    settings: Settings | None = None,
    provider: SandboxProvider | None = None,
    gateway: GatewayClient | None = None,
    store: Store | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        prov = provider or get_provider(settings.sandbox_provider)
        gw = gateway or (StubGateway() if settings.gateway_stub
                         else HttpGateway(settings.gateway_url, settings.gateway_admin_token))
        st = store
        if st is None and settings.database_url:
            from .store_pg import PostgresStore

            st = PostgresStore(settings.database_url)
            await st.open()
        orch = Orchestrator(settings, prov, gw, st or MemoryStore())
        ensure = getattr(prov, "ensure_infra", None)
        if ensure:
            await ensure()
        # Cajas huérfanas de un proceso anterior de este mismo ambiente. Si el provider no
        # responde, el servicio arranca igual: /health lo muestra y las corridas fallan con su error.
        try:
            for sb in await prov.list():
                if sb.spec.run_id not in orch.contexts:
                    await prov.destroy(sb)
        except Exception as e:
            print(f"aviso: no se pudieron limpiar cajas huérfanas: {type(e).__name__}: {e}", flush=True)
        orch.start()
        app.state.orch = orch
        yield
        await orch.stop()
        close = getattr(orch.store, "close", None)
        if close and store is None:
            await close()

    app = FastAPI(title="AIgis orquestador", lifespan=lifespan)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    def require_token(authorization: str = Header(default="")) -> None:
        """Con AIGIS_API_TOKEN definido se exige en toda la API pública salvo /health: lanzar gasta
        crédito y leer muestra payloads de ataque, eventos y diffs. El panel web lo agrega en su proxy."""
        if settings.api_token and not hmac.compare_digest(authorization.removeprefix("Bearer ").strip(),
                                                          settings.api_token):
            raise HTTPException(401, "token inválido")

    def orch(request: Request) -> Orchestrator:
        return request.app.state.orch

    def get_ctx(request: Request, run_id: str):
        rc = orch(request).contexts.get(run_id)
        if rc is None:
            raise HTTPException(404, "corrida no encontrada")
        return rc

    async def get_run_obj(request: Request, run_id: str):
        """Corrida viva si está en este proceso; si no, la guardada (p. ej. tras un reinicio)."""
        rc = orch(request).contexts.get(run_id)
        if rc is not None:
            return rc.run
        run = await orch(request).store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "corrida no encontrada")
        return run

    @app.get("/health")
    async def health(request: Request):
        o = orch(request)
        return {"ok": True, "provider": o.provider.name, "gateway_ok": await o.gateway.health(),
                "agent": settings.agent, "lanes": settings.lane_list, "model": settings.model}

    @app.get("/tasks", dependencies=[Depends(require_token)])
    async def tasks(request: Request):
        return [t.public() for t in orch(request).tasks.values()]

    @app.get("/lanes")
    async def lanes(request: Request):
        """Catálogo de carriles con su configuración, fuentes y huecos conocidos."""
        return {"default": settings.lane_list, "lanes": [s.public() for s in CATALOG.values()]}

    @app.get("/attacks", dependencies=[Depends(require_token)])
    async def attacks(request: Request):
        return [a.public() for a in orch(request).attacks.values()]

    @app.post("/runs", status_code=201, dependencies=[Depends(require_token)])
    async def create_run(req: RunRequest, request: Request):
        b = await orch(request).budget()
        if not b["live_enabled"]:
            # Mismo contrato que JudgeError (judges-access): la web lo maneja en un solo lugar
            return JSONResponse({"error": "budget", "detail": "se acabó el presupuesto de corridas en vivo; "
                                 "mira las grabaciones", "retry_after_s": None}, status_code=429)
        try:
            r = await orch(request).submit(req)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {"run_id": r.id, "queue_position": r.queue_position}

    @app.get("/runs", dependencies=[Depends(require_token)])
    async def list_runs(request: Request, limit: int = 50):
        runs = await orch(request).store.list_runs(limit)
        return [r.public() for r in runs]

    @app.get("/runs/{run_id}", dependencies=[Depends(require_token)])
    async def get_run(run_id: str, request: Request):
        return (await get_run_obj(request, run_id)).public()

    @app.post("/runs/{run_id}/cancel", dependencies=[Depends(require_token)])
    async def cancel_run(run_id: str, request: Request):
        get_ctx(request, run_id)
        return {"cancelled": await orch(request).cancel(run_id)}

    @app.get("/runs/{run_id}/events", dependencies=[Depends(require_token)])
    async def events(run_id: str, request: Request, after: int = 0, follow: bool = True,
                     last_event_id: str | None = Header(default=None)):
        o = orch(request)
        run = await get_run_obj(request, run_id)
        if last_event_id and last_event_id.isdigit():
            after = max(after, int(last_event_id))
        finished = run.status in ("done", "failed", "cancelled") or run_id not in o.contexts

        async def gen():
            yield "retry: 2000\n\n"
            async for ev in o.bus.subscribe(run_id, after, follow=follow and not finished):
                if await request.is_disconnected():
                    break
                yield f"id: {ev.seq}\nevent: {ev.type}\ndata: {ev.model_dump_json()}\n\n"
            yield "event: end\ndata: {}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/runs/{run_id}/lanes/{lane}/diff", response_class=PlainTextResponse, dependencies=[Depends(require_token)])
    async def lane_diff(run_id: str, lane: str, request: Request):
        run = await get_run_obj(request, run_id)
        role = "bajo" if lane == "gemelo" else "unico"
        diff = await orch(request).store.get_diff(run_id, lane, role)
        if diff is None:
            raise HTTPException(404, "sin diff")
        res = run.lanes[lane].result if lane in run.lanes else None
        if lane == "gemelo" and res is not None and not res.delivered:
            raise HTTPException(409, f"diff no entregado: {res.verdict}")
        return await orch(request).redact_persisted(run_id, diff)

    @app.get("/runs/{run_id}/usage", dependencies=[Depends(require_token)])
    async def run_usage(run_id: str, request: Request):
        """Uso real que reportó el gateway (claves de by_lane: "<carril>/<rol>" y "<carril>/monitor")."""
        await get_run_obj(request, run_id)
        u = await orch(request).store.get_usage(run_id)
        if u is None:
            raise HTTPException(404, "sin uso registrado")
        keep = ("cost_usd", "requests", "input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens", "by_lane")
        return {"run_id": run_id, **{k: u[k] for k in keep if k in u}}

    @app.get("/runs/{run_id}/chain", dependencies=[Depends(require_token)])
    async def run_chain(run_id: str, request: Request):
        """Cadena del ataque por carril y caja, armada desde los eventos guardados (ver chain.py)."""
        from .chain import build_chain
        from .divergence import hosts_of_urls

        run = await get_run_obj(request, run_id)
        events = await orch(request).store.events(run_id)
        return build_chain(events, run, ignore_hosts=hosts_of_urls(settings.gateway_url_sandbox,
                                                                   settings.hook_base_sandbox))

    @app.get("/budget", dependencies=[Depends(require_token)])
    async def budget(request: Request):
        return await orch(request).budget()

    @app.get("/queue", dependencies=[Depends(require_token)])
    async def queue(request: Request):
        return orch(request).queue()

    # ----- desde las cajas -----

    @app.post("/hooks/{run_id}/{lane}/{role}/{phase}")
    async def hook(run_id: str, lane: str, role: str, phase: str, request: Request,
                   authorization: str = Header(default="")):
        if phase not in ("pre", "post"):
            raise HTTPException(404)
        token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            payload = {}
        return await orch(request).handle_hook(run_id, lane, role, phase, token, payload)

    @app.api_route("/p/{run_id}/{path:path}", methods=["GET", "POST"], response_class=HTMLResponse)
    async def attack_page(run_id: str, path: str, request: Request):
        """Página de docs con el ataque (vector webpage). Solo desarrollo; en la demo la sirve el atacante.

        Cualquier dato que llegue en la query o el cuerpo se escanea como exfiltración.
        """
        o = orch(request)
        body = (await request.body()).decode("utf-8", "replace")
        raw = f"{request.url.query}\n{body}".strip()
        if raw:
            await o.leaks.scan_payload(raw, channel="page", at=time.time())
        page = o.pages.get((run_id, "/" + path))
        if page is None:
            raise HTTPException(404)
        return page

    # ----- webhooks -----

    def check_sig(body: bytes, sig: str) -> None:
        expected = "sha256=" + hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig or ""):
            raise HTTPException(401, "firma inválida")

    @app.post("/webhooks/attacker")
    async def attacker_hook(request: Request, x_aigis_signature: str = Header(default="")):
        body = await request.body()
        check_sig(body, x_aigis_signature)
        data = json.loads(body or b"{}")
        raw = str(data.get("raw", ""))
        at = float(data.get("received_at") or time.time())
        leaks = await orch(request).leaks.scan_payload(raw, channel=str(data.get("channel", "http")), at=at)
        return {"matched": [lk.id for lk in leaks]}

    @app.post("/webhooks/canary/{secret}")
    async def canary_hook(secret: str, request: Request):
        if not hmac.compare_digest(secret, settings.webhook_secret):
            raise HTTPException(401)
        try:
            data = await request.json()
        except Exception:
            data = dict(await request.form())
        cid = str(data.get("canary_id") or data.get("token") or data.get("memo") or "")
        lk = await orch(request).leaks.canary(cid) if cid else None
        return {"matched": lk.id if lk else None}

    @app.post("/internal/egress")
    async def egress(request: Request, authorization: str = Header(default="")):
        """Decisiones del proxy de salida (provider local)."""
        o = orch(request)
        token = getattr(o.provider, "admin_token", None)
        if not token or not hmac.compare_digest(authorization.removeprefix("Bearer ").strip(), token):
            raise HTTPException(401)
        await o.handle_egress(await request.json())
        return {"ok": True}

    @app.get("/dev/sandboxes", dependencies=[Depends(require_token)])
    async def dev_sandboxes(request: Request):
        if not settings.dev:
            raise HTTPException(404)
        return [{"id": sb.id, "run_id": sb.spec.run_id, "lane": sb.spec.lane, "role": sb.spec.role, "ip": sb.ip,
                 "network": (sb.network or sb.spec.network).label} for sb in await orch(request).provider.list()]

    return app


# El provider y el gateway se crean en el lifespan, no al importar
app = create_app()
