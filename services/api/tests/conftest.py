"""Arma un orquestador real (uvicorn en un hilo) con provider falso, gateway stub y
un atacante stub que reenvía todo lo recibido al webhook firmado del orquestador."""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
import uvicorn

from aigis.app import create_app
from aigis.config import REPO_ROOT, Settings
from aigis.gateway_client import StubGateway
from aigis.providers.fake import FakeProvider
from aigis.store import MemoryStore


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Harness:
    base: str
    settings: Settings
    provider: FakeProvider
    gateway: StubGateway
    store: MemoryStore
    attacker_hits: list[bytes]

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base, timeout=30)

    def wait_run(self, run_id: str, timeout: float = 120) -> dict:
        with self.client() as c:
            t0 = time.time()
            while time.time() - t0 < timeout:
                r = c.get(f"/runs/{run_id}").json()
                if r["status"] in ("done", "failed", "cancelled"):
                    return r
                time.sleep(0.3)
        raise TimeoutError(run_id)


def _attacker(port: int, orch_url: str, secret: str, hits: list[bytes]) -> http.server.HTTPServer:
    class H(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = (self.path + "\n").encode() + (self.rfile.read(n) if n else b"")
            hits.append(raw)
            body = json.dumps({"raw": raw.decode("utf-8", "replace"), "channel": "http",
                               "received_at": time.time()}).encode()
            sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            httpx.post(f"{orch_url}/webhooks/attacker", content=body,
                       headers={"X-Aigis-Signature": sig, "Content-Type": "application/json"})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        do_GET = do_POST = _handle

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def harness(tmp_path) -> Iterator[Harness]:
    port, aport = free_port(), free_port()
    settings = Settings(
        sandbox_provider="fake", public_host="127.0.0.1", port=port, gateway_stub=True,
        gateway_url_sandbox=f"http://127.0.0.1:{port}/gw", attacker_url_sandbox=f"http://127.0.0.1:{aport}",
        agent="scripted", leak_grace_s=1.0, high_grace_after_low_s=10, agent_timeout_s=60, test_timeout_s=60,
        tasks_dir=REPO_ROOT / "tasks", sandbox_dir=REPO_ROOT / "sandbox", webhook_secret="test-secret",
    )
    provider = FakeProvider(root=tmp_path / "boxes", gateway_hosts=(f"127.0.0.1:{port}",))
    gateway, store = StubGateway(), MemoryStore()
    app = create_app(settings, provider=provider, gateway=gateway, store=store)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    hits: list[bytes] = []
    atk = _attacker(aport, f"http://127.0.0.1:{port}", settings.webhook_secret, hits)
    yield Harness(f"http://127.0.0.1:{port}", settings, provider, gateway, store, hits)
    atk.shutdown()
    server.should_exit = True
    th.join(timeout=10)
