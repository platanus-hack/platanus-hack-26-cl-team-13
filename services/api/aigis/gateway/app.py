"""App FastAPI del gateway: rutas /admin para el orquestador y /v1/messages para las cajas."""

from __future__ import annotations

import hmac
import json
import logging
import math
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .config import GatewaySettings, get_gateway_settings
from .pricing import PriceTable, Usage
from .tokens import Denied, Reservation, TokenRecord, TokenStore, clean_lane

log = logging.getLogger("aigis.gateway")

# Headers del cliente que se reenvían al upstream. Todo lo demás se descarta, en especial
# Authorization, x-api-key y X-Aigis-Lane. anthropic-beta NO se reenvía: habilita rasgos
# beta (ej. web_search/web_fetch de servidor) que serían un canal de salida para una caja
# aislada; el gateway es la única puerta del gemelo bajo y decide qué rasgos existen.
FORWARD_REQ = ("anthropic-version", "content-type", "accept")

# Herramientas de SERVIDOR: las ejecuta el upstream (sus servidores) y harían peticiones
# externas desde fuera del sandbox. Son el canal por el que una caja sin internet podría
# exfiltrar via el gateway. Se eliminan del body; las tools del cliente (custom) pasan.
_SERVER_TOOL = re.compile(r"^(web_search|web_fetch|web_search_2|computer_|code_execution|bash_|text_editor)")


def sanitize_body(body: dict) -> dict:
    body.pop("mcp_servers", None)
    tools = body.get("tools")
    if isinstance(tools, list):
        body["tools"] = [t for t in tools
                         if not (isinstance(t, dict) and _SERVER_TOOL.match(str(t.get("type", ""))))]
    return body
FORWARD_RESP = ("content-type", "request-id", "retry-after", "anthropic-organization-id")


def api_error(status: int, kind: str, message: str) -> JSONResponse:
    # x-should-retry=false: Claude Code y los SDK no reintentan un 401/402/403 del gateway
    return JSONResponse({"type": "error", "error": {"type": kind, "message": message}},
                        status_code=status, headers={"x-should-retry": "false"})


class IssueRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    budget_usd: float | None = Field(default=None, gt=0)
    ttl_s: int | None = Field(default=None, gt=0)
    lane: str | None = None
    role: str | None = None


class SSEUsage:
    """Lee el stream SSE de Anthropic a medida que pasa y junta el `usage`.

    message_start trae la entrada (y caché); message_delta trae la salida acumulada.
    """

    def __init__(self) -> None:
        self.buf = b""
        self.usage = Usage()
        self.model: str | None = None
        self.done = False
        self.error = False

    def feed(self, chunk: bytes) -> None:
        self.buf += chunk.replace(b"\r\n", b"\n")
        while b"\n\n" in self.buf:
            frame, self.buf = self.buf.split(b"\n\n", 1)
            data = b"\n".join(l[5:].lstrip() for l in frame.split(b"\n") if l.startswith(b"data:"))
            if not data:
                continue
            try:
                ev = json.loads(data)
            except ValueError:
                continue
            t = ev.get("type")
            if t == "message_start":
                msg = ev.get("message") or {}
                self.model = msg.get("model") or self.model
                self.usage.merge(msg.get("usage"))
            elif t == "message_delta":
                self.usage.merge(ev.get("usage"))
            elif t == "message_stop":
                self.done = True
            elif t == "error":
                self.error = True


def create_gateway_app(settings: GatewaySettings | None = None,
                       transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    s = settings or get_gateway_settings()
    prices = PriceTable(s.prices_json)
    store = TokenStore(retain_s=s.retain_s)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(s.upstream_timeout_s, connect=10.0))
        yield
        await app.state.http.aclose()

    app = FastAPI(title="AIgis gateway", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.settings = s

    # ---------- admin ----------

    def admin_ok(req: Request) -> JSONResponse | None:
        expected = s.admin_token.get_secret_value()
        if not expected:
            return api_error(503, "api_error", "admin deshabilitado: falta GATEWAY_ADMIN_TOKEN")
        got = req.headers.get("authorization", "")
        if not hmac.compare_digest(got.encode(), f"Bearer {expected}".encode()):
            return api_error(401, "authentication_error", "admin token inválido")
        return None

    @app.get("/health")
    async def health():
        return {"ok": True, "upstream_configured": bool(s.upstream_api_key.get_secret_value()),
                "model": s.model}

    @app.post("/admin/tokens")
    async def issue(req: Request, body: IssueRequest):
        if (e := admin_ok(req)) is not None:
            return e
        budget = min(body.budget_usd or s.default_budget_usd, s.max_budget_usd)
        ttl = min(body.ttl_s or s.default_ttl_s, s.max_ttl_s)
        lane = None
        if body.lane:
            lane = clean_lane(f"{body.lane}/{body.role}" if body.role else body.lane)
            if lane == "unknown":
                return api_error(400, "invalid_request_error", "lane/role inválidos")
        token, rec = await store.issue(body.run_id, budget, ttl, lane)
        log.info("token emitido run=%s lane=%s budget=%.2f ttl=%d", rec.run_id, lane, budget, ttl)
        return {"token": token, "expires_at": rec.expires_at, "budget_usd": budget}

    @app.delete("/admin/tokens/{token}")
    async def revoke(req: Request, token: str):
        if (e := admin_ok(req)) is not None:
            return e
        await store.revoke(token)  # idempotente: 204 aunque no exista
        return Response(status_code=204)

    @app.get("/admin/tokens/{token}/usage")
    async def token_usage(req: Request, token: str):
        if (e := admin_ok(req)) is not None:
            return e
        rec = store.get(token)
        if rec is None:
            return api_error(404, "not_found_error", "token desconocido")
        return rec.usage(store.clock())

    @app.delete("/admin/runs/{run_id}")
    async def revoke_run(req: Request, run_id: str):
        if (e := admin_ok(req)) is not None:
            return e
        return {"revoked": await store.revoke_run(run_id)}

    @app.get("/admin/runs/{run_id}/usage")
    async def run_usage(req: Request, run_id: str):
        if (e := admin_ok(req)) is not None:
            return e
        recs = store.by_run(run_id)
        now = store.clock()
        by_lane: dict[str, dict] = {}
        for r in recs:
            for k, v in r.usage(now)["by_lane"].items():
                acc = by_lane.setdefault(k, {f: 0 for f in v})
                for f, x in v.items():
                    acc[f] += x
        return {"run_id": run_id, "tokens": len(recs),
                "cost_usd": round(sum(r.spent_usd for r in recs), 6),
                "requests": sum(r.requests for r in recs), "by_lane": by_lane}

    # ---------- proxy ----------

    def bearer(req: Request) -> str:
        auth = req.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return req.headers.get("x-api-key", "").strip()

    def lane_of(rec: TokenRecord, req: Request) -> str:
        return rec.lane or clean_lane(req.headers.get("x-aigis-lane"))

    def upstream_headers(req: Request) -> dict[str, str]:
        h = {k: req.headers[k] for k in FORWARD_REQ if k in req.headers}
        h.setdefault("anthropic-version", "2023-06-01")
        h["x-api-key"] = s.upstream_api_key.get_secret_value()
        return h

    def resp_headers(r: httpx.Response) -> dict[str, str]:
        return {k: r.headers[k] for k in FORWARD_RESP if k in r.headers}

    async def read_json(req: Request) -> tuple[dict, int] | JSONResponse:
        raw = await req.body()
        try:
            body = json.loads(raw)
        except ValueError:
            return api_error(400, "invalid_request_error", "cuerpo JSON inválido")
        if not isinstance(body, dict):
            return api_error(400, "invalid_request_error", "cuerpo JSON inválido")
        return body, len(raw)

    def pin_model(body: dict) -> str:
        asked = body.get("model")
        model = asked if asked in s.allowed_model_set else s.model
        body["model"] = model
        return model

    def upstream_failed(status: int, content: bytes, headers: dict[str, str]) -> Response:
        # Un 401/403 del upstream es un problema de la key del gateway, no del token de la
        # caja: se informa como 502 para que el agente no crea que su token es malo.
        if status in (401, 403):
            log.error("upstream rechazó la key del gateway (status %d)", status)
            return api_error(502, "api_error", "el gateway no pudo autenticarse con el upstream")
        return Response(content=content, status_code=status, headers=headers)

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(req: Request):
        try:
            store.authenticate(bearer(req))
        except Denied as d:
            return api_error(d.status, d.kind, d.message)
        parsed = await read_json(req)
        if isinstance(parsed, JSONResponse):
            return parsed
        body, _ = parsed
        pin_model(body)
        sanitize_body(body)
        q = f"?{req.url.query}" if req.url.query else ""
        r = await app.state.http.post(f"{s.upstream_base}/v1/messages/count_tokens{q}",
                                      json=body, headers=upstream_headers(req))
        if r.status_code >= 400:
            return upstream_failed(r.status_code, r.content, resp_headers(r))
        return Response(content=r.content, status_code=r.status_code, headers=resp_headers(r))

    @app.post("/v1/messages")
    async def messages(req: Request):
        try:
            rec = store.authenticate(bearer(req))
        except Denied as d:
            return api_error(d.status, d.kind, d.message)
        parsed = await read_json(req)
        if isinstance(parsed, JSONResponse):
            return parsed
        body, nbytes = parsed
        model = pin_model(body)
        sanitize_body(body)
        lane = lane_of(rec, req)

        # Reserva del peor caso. Se recorta max_tokens para que la salida quepa en el saldo:
        # así el tope en USD se cumple aunque haya varias llamadas en paralelo.
        in_cost = prices.worst_case_input(model, nbytes)
        out_tok = prices.output_per_token(model, nbytes)
        room = rec.remaining_usd - in_cost
        fit = math.floor(room / out_tok) if room > 0 else 0
        asked = body.get("max_tokens")
        asked = asked if isinstance(asked, int) and asked > 0 else 4096
        if fit < min(asked, s.min_output_tokens):
            rec.cut = "budget"
            log.warning("corte por presupuesto run=%s lane=%s", rec.run_id, lane)
            return api_error(402, "billing_error", f"tope de gasto del token alcanzado (USD {rec.budget_usd:.2f})")
        max_tokens = min(asked, fit)
        body["max_tokens"] = max_tokens
        thinking = body.get("thinking")
        if isinstance(thinking, dict) and isinstance(thinking.get("budget_tokens"), int):
            thinking["budget_tokens"] = min(thinking["budget_tokens"], max(1024, max_tokens - 1))
        try:
            res = await store.reserve(rec, lane, in_cost + max_tokens * out_tok, s.max_requests)
        except Denied as d:
            log.warning("rechazo run=%s lane=%s: %s", rec.run_id, lane, d.kind)
            return api_error(d.status, d.kind, d.message)

        # Claude Code llama /v1/messages?beta=true: se conserva la query
        url = f"{s.upstream_base}/v1/messages" + (f"?{req.url.query}" if req.url.query else "")
        headers = upstream_headers(req)
        if body.get("stream"):
            return await stream_messages(res, model, url, headers, body)
        try:
            r = await app.state.http.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            await store.release(res)
            log.error("upstream inalcanzable: %s", type(e).__name__)
            return api_error(502, "api_error", "upstream inalcanzable")
        if r.status_code >= 400:
            await store.release(res)
            return upstream_failed(r.status_code, r.content, resp_headers(r))
        u = Usage()
        try:
            data = r.json()
            u.merge(data.get("usage"))
            used_model = data.get("model") or model
        except ValueError:
            data, used_model = None, model
        cost = prices.cost(used_model, u) if data is not None else None
        await store.settle(res, u, cost)
        log_call(rec, lane, used_model, u, cost if cost is not None else res.amount, stream=False)
        return Response(content=r.content, status_code=r.status_code, headers=resp_headers(r))

    async def stream_messages(res: Reservation, model: str, url: str, headers: dict, body: dict):
        http: httpx.AsyncClient = app.state.http
        try:
            r = await http.send(http.build_request("POST", url, json=body, headers=headers), stream=True)
        except httpx.HTTPError as e:
            await store.release(res)
            log.error("upstream inalcanzable: %s", type(e).__name__)
            return api_error(502, "api_error", "upstream inalcanzable")
        if r.status_code >= 400:
            content = await r.aread()
            await r.aclose()
            await store.release(res)
            return upstream_failed(r.status_code, content, resp_headers(r))

        parser = SSEUsage()

        async def relay() -> AsyncIterator[bytes]:
            try:
                async for chunk in r.aiter_bytes():  # decodificado: no se reenvía content-encoding
                    parser.feed(chunk)
                    yield chunk
            finally:
                await r.aclose()
                used = parser.model or model
                # Stream completo: costo real. Cortado (cliente se fue, error de red): se cobra
                # el máximo entre lo visto y la reserva, porque el upstream pudo seguir generando.
                cost = prices.cost(used, parser.usage)
                if not parser.done:
                    cost = max(cost, res.amount)
                await store.settle(res, parser.usage, cost)
                log_call(res.rec, res.lane, used, parser.usage, cost, stream=True, complete=parser.done)

        h = resp_headers(r)
        h.setdefault("content-type", "text/event-stream")
        h["cache-control"] = "no-cache"
        h["x-accel-buffering"] = "no"
        return StreamingResponse(relay(), status_code=r.status_code, headers=h)

    def log_call(rec: TokenRecord, lane: str, model: str, u: Usage, cost: float, *, stream: bool,
                 complete: bool = True) -> None:
        log.info("llamada run=%s lane=%s model=%s in=%d out=%d cw=%d cr=%d usd=%.5f stream=%s ok=%s spent=%.4f/%.2f",
                 rec.run_id, lane, model, u.input_tokens, u.output_tokens, u.cache_creation_input_tokens,
                 u.cache_read_input_tokens, cost, stream, complete, rec.spent_usd, rec.budget_usd)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def unknown(path: str):
        return api_error(404, "not_found_error", "ruta no soportada por el gateway")

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_gateway_app()
