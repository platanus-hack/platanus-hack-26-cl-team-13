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
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .gateway_client import GatewayClient, HttpGateway, StubGateway
from .lanes.catalog import CATALOG
from .judges import JUDGE_PREFIX, JudgeDesk, Scrubber, check_token, clean_payload, public_event, public_run
from .models import Attack, AttackVector, RunRequest
from .providers import SandboxProvider, get_provider
from .runner import Orchestrator
from .store import MemoryStore, Store


class JudgeRunRequest(BaseModel):
    task_id: str
    vector: AttackVector | None = None
    payload: str | None = Field(default=None, max_length=8192)
    # Ataque del catálogo como alternativa a escribir uno
    attack_id: str | None = None


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
        app.state.judges = JudgeDesk(settings)
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
                "agent": settings.agent, "lanes": settings.lane_list}

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

    @app.get("/queue", dependencies=[Depends(require_token)])
    async def queue(request: Request):
        return orch(request).queue()

    # ----- jueces: token corto por juez (aigis/judges.py) -----

    scrub = Scrubber(settings)
    HISTORY = 500

    def require_judge(authorization: str = Header(default="")) -> str:
        alias = check_token(settings, authorization.removeprefix("Bearer ").strip())
        if alias is None:
            raise HTTPException(401, "token de juez inválido")
        return alias

    def desk(request: Request) -> JudgeDesk:
        return request.app.state.judges

    def judge_tasks(request: Request) -> list:
        allowed = settings.judge_task_list
        return [t for t in orch(request).tasks.values() if not allowed or t.id in allowed]

    def sse(request: Request, run_id: str, finished: bool, after: int, transform=None):
        o = orch(request)

        async def gen():
            yield "retry: 2000\n\n"
            async for ev in o.bus.subscribe(run_id, after, follow=not finished):
                if await request.is_disconnected():
                    break
                if transform is None:
                    yield f"id: {ev.seq}\nevent: {ev.type}\ndata: {ev.model_dump_json()}\n\n"
                    continue
                pub = transform(ev)
                if pub is not None:
                    yield f"id: {ev.seq}\nevent: {ev.type}\ndata: {json.dumps(pub, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: {}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/j/me")
    async def judge_me(request: Request, alias: str = Depends(require_judge)):
        return desk(request).status(alias, await orch(request).store.list_runs(HISTORY))

    @app.get("/j/tasks", dependencies=[Depends(require_judge)])
    async def judge_task_list(request: Request):
        return [t.public() for t in judge_tasks(request)]

    @app.get("/j/attacks", dependencies=[Depends(require_judge)])
    async def judge_attacks(request: Request):
        """Catálogo con el payload completo, para partir de un ataque y editarlo."""
        return [a.model_dump(include={"id", "title", "technique", "channel", "vectors", "payload"})
                for a in orch(request).attacks.values()]

    @app.post("/j/runs", status_code=201)
    async def judge_run(req: JudgeRunRequest, request: Request, alias: str = Depends(require_judge)):
        o, d = orch(request), desk(request)
        if req.task_id not in {t.id for t in judge_tasks(request)}:
            raise HTTPException(404, f"tarea no disponible: {req.task_id}")
        author = f"{JUDGE_PREFIX}{alias}"
        if req.attack_id:
            if req.payload:
                raise HTTPException(422, "usa payload o attack_id, no ambos")
            cat = o.attacks.get(req.attack_id)
            if cat is None:
                raise HTTPException(404, f"ataque desconocido: {req.attack_id}")
            task = o.tasks[req.task_id]
            vec = req.vector if req.vector in cat.vectors else next((v for v in cat.vectors if v in task.vectors), None)
            if vec is None:
                raise HTTPException(422, f"el ataque {cat.id} no comparte vector con la tarea {task.id}")
            attack = cat.to_attack(vec).model_copy(update={"author": author})
        else:
            payload = clean_payload(req.payload or "").strip()
            if not payload or req.vector is None:
                raise HTTPException(422, "falta vector y payload, o attack_id")
            attack = Attack(vector=req.vector, payload=payload, author=author)
        try:
            d.check(alias, await o.store.list_runs(HISTORY))
        except ValueError as e:
            raise HTTPException(429, str(e)) from e
        d.mark(alias)
        try:
            r = await o.submit(RunRequest(task_id=req.task_id, attack=attack, lanes=settings.judge_lane_list))
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {"run_id": r.id, "queue_position": r.queue_position}

    @app.get("/j/runs")
    async def judge_runs(request: Request, alias: str = Depends(require_judge)):
        runs = await orch(request).store.list_runs(HISTORY)
        mine = [r for r in runs if r.attack and r.attack.author == f"{JUDGE_PREFIX}{alias}"]
        return [public_run(r, scrub, preview=8192) for r in mine]

    @app.post("/admin/judges/pause", dependencies=[Depends(require_token)])
    async def judges_pause(request: Request, paused: bool = True):
        desk(request).paused = paused
        return {"paused": paused}

    # ----- vista pública: sin token, recortada por lista blanca -----

    @app.get("/public/runs")
    async def public_runs(request: Request, limit: int = 30):
        runs = await orch(request).store.list_runs(max(1, min(limit, 100)))
        return [public_run(r, scrub, settings.public_payload_preview) for r in runs]

    @app.get("/public/runs/{run_id}")
    async def public_run_one(run_id: str, request: Request):
        return public_run(await get_run_obj(request, run_id), scrub, settings.public_payload_preview)

    @app.get("/public/runs/{run_id}/events")
    async def public_events(run_id: str, request: Request, after: int = 0, follow: bool = True,
                            last_event_id: str | None = Header(default=None)):
        run = await get_run_obj(request, run_id)
        if last_event_id and last_event_id.isdigit():
            after = max(after, int(last_event_id))
        finished = run.status in ("done", "failed", "cancelled") or run_id not in orch(request).contexts
        return sse(request, run_id, finished or not follow, after, lambda ev: public_event(ev, scrub))

    @app.get("/public/queue")
    async def public_queue(request: Request):
        return {"length": len(orch(request).queue()), "judges_open": not desk(request).paused
                and bool(settings.judge_secret)}

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
