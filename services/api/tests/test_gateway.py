"""Gateway del modelo contra un upstream falso (httpx.MockTransport), sin red."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gemelo.gateway.app import SSEUsage, create_gateway_app
from gemelo.gateway.config import GatewaySettings
from gemelo.gateway.pricing import PriceTable, Usage

ADMIN = "admin-test-token"
UPSTREAM_KEY = "sk-ant-test-upstream-key-NO-DEBE-SALIR"
PHK = "phk_secreto_de_la_hackaton"
A = {"Authorization": f"Bearer {ADMIN}"}


def sse(events: list[dict]) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def stream_events(text: str = "hola", inp: int = 1000, out: int = 50, model: str = "claude-haiku-5-5") -> list[dict]:
    return [
        {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": model,
                                              "content": [], "usage": {"input_tokens": inp, "output_tokens": 1,
                                                                       "cache_read_input_tokens": 0,
                                                                       "cache_creation_input_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "ping"},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": out}},
        {"type": "message_stop"},
    ]


class Upstream:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.status = 200
        self.usage = {"input_tokens": 1000, "output_tokens": 50}

    async def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        if self.status != 200:
            return httpx.Response(self.status, json={"type": "error", "error": {"type": "x", "message": "upstream"}})
        body = json.loads(req.content)
        if req.url.path.endswith("/count_tokens"):
            return httpx.Response(200, json={"input_tokens": 42})
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream", "request-id": "req_up"},
                                  stream=httpx.ByteStream(sse(stream_events(
                                      inp=self.usage["input_tokens"], out=self.usage["output_tokens"], model=body["model"]))))
        return httpx.Response(200, headers={"request-id": "req_up"}, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": "hola"}], "stop_reason": "end_turn", "usage": self.usage})


@pytest.fixture
def up() -> Upstream:
    return Upstream()


@pytest.fixture
def client(up: Upstream):
    s = GatewaySettings(admin_token=ADMIN, upstream_api_key=UPSTREAM_KEY,
                        upstream_url=f"https://llm.example.test/t/{PHK}/anthropic", _env_file=None)
    app = create_gateway_app(s, transport=httpx.MockTransport(up.handler))
    with TestClient(app) as c:
        yield c


def issue(c: TestClient, run_id: str = "run1", budget: float = 1.0, ttl: int = 600, **kw) -> str:
    r = c.post("/admin/tokens", headers=A, json={"run_id": run_id, "budget_usd": budget, "ttl_s": ttl, **kw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def msg(c: TestClient, token: str | None, lane: str = "gemelo/low", stream: bool = False, model: str = "claude-opus-5-5",
        max_tokens: int = 1000, query: str = "") -> httpx.Response:
    h = {"anthropic-version": "2023-06-01", "X-Gemelo-Lane": lane}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return c.post("/v1/messages" + query, headers=h, json={
        "model": model, "max_tokens": max_tokens, "stream": stream,
        "messages": [{"role": "user", "content": "hola"}]})


# ---------- admin ----------

def test_admin_requiere_token(client):
    assert client.post("/admin/tokens", json={"run_id": "r"}).status_code == 401
    assert client.post("/admin/tokens", headers={"Authorization": "Bearer otro"}, json={"run_id": "r"}).status_code == 401


def test_admin_deshabilitado_sin_token(up):
    s = GatewaySettings(admin_token="", _env_file=None)
    with TestClient(create_gateway_app(s, transport=httpx.MockTransport(up.handler))) as c:
        assert c.post("/admin/tokens", headers=A, json={"run_id": "r"}).status_code == 503


def test_tope_de_emision(client):
    r = client.post("/admin/tokens", headers=A, json={"run_id": "r", "budget_usd": 999, "ttl_s": 10**9})
    assert r.json()["budget_usd"] == 20.0


# ---------- autenticación (escenarios del spec) ----------

def test_sin_token_401_y_no_llama_al_modelo(client, up):
    r = msg(client, None)
    assert r.status_code == 401 and r.json()["error"]["type"] == "authentication_error"
    assert msg(client, "gw_inventado").status_code == 401
    assert up.calls == []


def test_token_por_x_api_key(client):
    tok = issue(client)
    r = client.post("/v1/messages", headers={"x-api-key": tok}, json={
        "model": "x", "max_tokens": 10, "messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200


def test_token_revocado_401(client, up):
    tok = issue(client)
    assert msg(client, tok).status_code == 200
    assert client.delete(f"/admin/tokens/{tok}", headers=A).status_code == 204
    r = msg(client, tok)
    assert r.status_code == 401 and r.headers["x-should-retry"] == "false"
    assert len(up.calls) == 1


def test_token_expirado_401(client):
    tok = issue(client)
    store = client.app.state.store
    store.clock = lambda: 10**12
    assert msg(client, tok).status_code == 401


def test_revocar_corrida_completa(client):
    t1, t2 = issue(client, "rA", lane="none", role="solo"), issue(client, "rA", lane="gemelo", role="high")
    t3 = issue(client, "rB")
    assert client.delete("/admin/runs/rA", headers=A).json() == {"revoked": 2}
    assert msg(client, t1).status_code == 401 and msg(client, t2).status_code == 401
    assert msg(client, t3).status_code == 200


def test_uso_queda_en_la_corrida_del_token(client):
    ta, tb = issue(client, "A"), issue(client, "B")
    msg(client, ta, lane="gemelo/low")
    ua = client.get(f"/admin/tokens/{ta}/usage", headers=A).json()
    ub = client.get(f"/admin/tokens/{tb}/usage", headers=A).json()
    assert ua["run_id"] == "A" and ua["requests"] == 1 and ua["cost_usd"] > 0
    assert ub["requests"] == 0 and ub["cost_usd"] == 0


# ---------- proxy ----------

def test_modelo_fijado_y_headers_limpios(client, up):
    tok = issue(client)
    r = msg(client, tok, model="claude-opus-5-5", query="?beta=true")
    assert r.status_code == 200
    req = up.calls[0]
    assert json.loads(req.content)["model"] == "claude-haiku-5-5"
    assert req.url.path == f"/t/{PHK}/anthropic/v1/messages" and req.url.query == b"beta=true"
    assert req.headers["x-api-key"] == UPSTREAM_KEY
    assert "authorization" not in req.headers and "x-gemelo-lane" not in req.headers
    assert tok not in req.content.decode() and tok not in str(req.headers)


def test_la_key_no_sale_en_respuestas(client, up):
    tok = issue(client)
    for r in (msg(client, tok), msg(client, tok, stream=True),
              client.get(f"/admin/tokens/{tok}/usage", headers=A), client.get("/health")):
        dump = r.text + json.dumps(dict(r.headers))
        assert UPSTREAM_KEY not in dump and PHK not in dump
    up.status = 401
    r = msg(client, tok)
    assert r.status_code == 502 and UPSTREAM_KEY not in r.text


def test_streaming_reenvia_y_cuenta(client):
    tok = issue(client)
    r = msg(client, tok, stream=True)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith("data:")]
    assert [e["type"] for e in events][-1] == "message_stop"
    u = client.get(f"/admin/tokens/{tok}/usage", headers=A).json()
    assert u["input_tokens"] == 1000 and u["output_tokens"] == 50
    expected = PriceTable().cost("claude-haiku-5-5", Usage(input_tokens=1000, output_tokens=50))
    assert u["cost_usd"] == pytest.approx(expected)
    assert u["by_lane"]["gemelo/low"]["requests"] == 1


def test_carril_fijado_en_token_ignora_header(client):
    tok = issue(client, lane="gemelo", role="high")
    msg(client, tok, lane="none/solo")
    u = client.get(f"/admin/tokens/{tok}/usage", headers=A).json()
    assert list(u["by_lane"]) == ["gemelo/high"]


def test_uso_por_corrida(client):
    t1, t2 = issue(client, "R", lane="none", role="solo"), issue(client, "R", lane="monitor", role="solo")
    msg(client, t1), msg(client, t2), msg(client, t2, stream=True)
    u = client.get("/admin/runs/R/usage", headers=A).json()
    assert u["requests"] == 3 and set(u["by_lane"]) == {"none/solo", "monitor/solo"}
    assert u["by_lane"]["monitor/solo"]["requests"] == 2


def test_count_tokens_no_cobra(client):
    tok = issue(client)
    r = client.post("/v1/messages/count_tokens", headers={"Authorization": f"Bearer {tok}"},
                    json={"model": "x", "messages": [{"role": "user", "content": "hola"}]})
    assert r.json() == {"input_tokens": 42}
    assert client.get(f"/admin/tokens/{tok}/usage", headers=A).json()["requests"] == 0


def test_ruta_desconocida_404(client):
    assert client.get("/v1/models").status_code == 404


def test_error_del_upstream_libera_reserva(client, up):
    tok = issue(client)
    up.status = 529
    assert msg(client, tok).status_code == 529
    u = client.get(f"/admin/tokens/{tok}/usage", headers=A).json()
    assert u["requests"] == 0 and u["remaining_usd"] == 1.0


# ---------- topes ----------

def test_recorta_max_tokens_al_saldo(client, up):
    # USD 0.001 alcanza para ~1900 tokens de salida de Haiku 5.5 tras la reserva de entrada
    tok = issue(client, budget=0.001)
    assert msg(client, tok, max_tokens=64000).status_code == 200
    sent = json.loads(up.calls[0].content)["max_tokens"]
    assert 256 <= sent < 2000


def test_tope_alcanzado_402(client, up):
    tok = issue(client, budget=0.0005)
    up.usage = {"input_tokens": 100, "output_tokens": 900}
    assert msg(client, tok).status_code == 200
    r = msg(client, tok)
    assert r.status_code == 402 and r.json()["error"]["type"] == "billing_error"
    assert len(up.calls) == 1
    u = client.get(f"/admin/tokens/{tok}/usage", headers=A).json()
    assert u["cut"] == "budget" and u["cost_usd"] <= 0.0005


def test_tope_de_llamadas(up):
    s = GatewaySettings(admin_token=ADMIN, upstream_api_key=UPSTREAM_KEY, max_requests=2, _env_file=None)
    with TestClient(create_gateway_app(s, transport=httpx.MockTransport(up.handler))) as c:
        tok = issue(c)
        assert msg(c, tok).status_code == 200 and msg(c, tok).status_code == 200
        r = msg(c, tok)
        assert r.status_code == 403 and len(up.calls) == 2


# ---------- unidades ----------

def test_sse_parser_en_trozos():
    raw = sse(stream_events(inp=10, out=7))
    p = SSEUsage()
    for i in range(0, len(raw), 13):
        p.feed(raw[i:i + 13])
    assert p.done and p.usage.input_tokens == 10 and p.usage.output_tokens == 7


def test_precio_cache_y_contexto_largo():
    t = PriceTable()
    base = t.cost("claude-haiku-5-5", Usage(input_tokens=50_000))
    assert base == pytest.approx(0.005)
    cached = t.cost("claude-haiku-5-5", Usage(input_tokens=1, cache_read_input_tokens=50_000))
    assert cached < t.cost("claude-haiku-5-5", Usage(input_tokens=50_001))
    long = t.cost("claude-haiku-5-5", Usage(input_tokens=200_000))
    assert long == pytest.approx(200_000 * 0.10 * 5 / 1e6)
    assert t.cost("modelo-raro", Usage(input_tokens=1000)) > t.cost("claude-opus-5-5", Usage(input_tokens=1000))
