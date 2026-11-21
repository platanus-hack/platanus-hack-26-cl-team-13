"""Sink publico que recibe exfiltraciones.

Hace de servidor del atacante: acepta cualquier GET o POST, guarda lo recibido y lo
reenvía firmado (HMAC-SHA256 con AIGIS_WEBHOOK_SECRET) a /webhooks/attacker del
orquestador, que busca ahí los secretos de la corrida y atribuye la filtración.

Solo biblioteca estándar. Variables:
  ATTACKER_PORT          puerto (9000)
  AIGIS_ORCH_URL         base del orquestador (http://api:8000)
  AIGIS_WEBHOOK_SECRET   mismo valor que el orquestador
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import os
import threading
import time
import urllib.request

PORT = int(os.environ.get("ATTACKER_PORT", "9000"))
ORCH = os.environ.get("AIGIS_ORCH_URL", "http://127.0.0.1:8000").rstrip("/")
SECRET = os.environ.get("AIGIS_WEBHOOK_SECRET", "dev-webhook-secret")
MAX_BODY = 1 << 20


def report(raw: bytes) -> None:
    body = json.dumps({"raw": raw.decode("utf-8", "replace"), "channel": "http", "received_at": time.time()}).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{ORCH}/webhooks/attacker", data=body, method="POST",
                                 headers={"X-Aigis-Signature": sig, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"sink: {len(raw)} bytes -> orquestador {r.status} {r.read(200)!r}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"sink: no se pudo avisar al orquestador: {type(e).__name__}: {e}", flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def _handle(self) -> None:
        n = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        raw = (self.path + "\n").encode() + (self.rfile.read(n) if n else b"")
        threading.Thread(target=report, args=(raw,), daemon=True).start()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = do_POST = do_PUT = _handle

    def log_message(self, fmt, *args):
        print(f"sink: {self.client_address[0]} {fmt % args}", flush=True)


def main() -> None:
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"sink del atacante en :{PORT}, reporta a {ORCH}/webhooks/attacker", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
