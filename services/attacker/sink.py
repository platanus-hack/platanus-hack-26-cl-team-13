"""Sink público que recibe exfiltraciones.

Servidor del atacante, black-box respecto de los carriles: acepta cualquier GET/POST/PUT
en cualquier ruta, persiste el hito crudo ANTES de analizar, decodifica capas localmente
(decoders.py) y reenvía raw + capas firmadas (HMAC-SHA256 con AIGIS_WEBHOOK_SECRET) a
/webhooks/attacker del orquestador, que empareja contra los secretos de la corrida.

Responde 200 siempre: un C2 que rechaza requests sube el FNR del ataque y contamina la
comparación entre carriles. Solo biblioteca estándar. Variables:
  ATTACKER_PORT          puerto (9000)
  AIGIS_ORCH_URL         base del orquestador (http://api:8000)
  AIGIS_WEBHOOK_SECRET   mismo valor que el orquestador
  ATTACKER_LOG           archivo JSONL de hitos (data/hits.jsonl; fallback /tmp)
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

import decoders
from sessions import SessionStore

PORT = int(os.environ.get("ATTACKER_PORT", "9000"))
ORCH = os.environ.get("AIGIS_ORCH_URL", "http://127.0.0.1:8000").rstrip("/")
SECRET = os.environ.get("AIGIS_WEBHOOK_SECRET", "dev-webhook-secret")
MAX_BODY = 1 << 20
MAX_LAYERS_SENT = 24
_HEADS = ("x-aigis-lane", "user-agent", "content-type")

LOG_PATH = os.environ.get("ATTACKER_LOG", "data/hits.jsonl")
_sessions = SessionStore()
_log_lock = threading.Lock()


def _log_path() -> str:
    global LOG_PATH
    try:
        d = os.path.dirname(LOG_PATH) or "."
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".w")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return LOG_PATH
    except OSError:
        LOG_PATH = os.path.join("/tmp" if os.name != "nt" else os.environ.get("TEMP", "."), "aigis-attacker-hits.jsonl")
        return LOG_PATH


def _persist(record: dict) -> None:
    try:
        with _log_lock:
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:  # noqa: BLE001
        print(f"sink: no se pudo persistir: {type(e).__name__}: {e}", flush=True)


def report(raw_text: str, *, path: str, ip: str, lane: str, received_at: float) -> None:
    """Decodifica, reconstruye la sesión y manda raw + capas al orquestador."""
    layers = decoders.layers(raw_text)[:MAX_LAYERS_SENT]
    skey = f"{ip}|{lane}"
    tail = _sessions.add(skey, raw_text, received_at)
    if tail != raw_text:
        layers = [*layers, ("session", tail)][:MAX_LAYERS_SENT + 1]
    body = json.dumps({
        "raw": raw_text,
        "channel": "http",
        "received_at": received_at,
        "session": skey,
        "layers": [{"encoding": lab, "text": t} for lab, t in layers],
    }).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{ORCH}/webhooks/attacker", data=body, method="POST",
                                 headers={"X-Aigis-Signature": sig, "Content-Type": "application/json"})
    matched: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read(4096) or b"{}")
            matched = [str(m) for m in resp.get("matched", [])]
    except Exception as e:  # noqa: BLE001
        print(f"sink: no se pudo avisar al orquestador: {type(e).__name__}: {e}", flush=True)
    _persist({"ts": received_at, "path": path, "ip": ip, "lane": lane, "session": skey,
              "encodings": [lab for lab, _ in layers], "matched": matched,
              "bytes": len(raw_text)})
    if matched:
        print(f"sink: MATCH {matched} en {path} (encodings: {[lab for lab, _ in layers]})", flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle(self) -> None:
        n = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        body = self.rfile.read(n) if n else b""
        path = self.path
        ip = self.client_address[0]
        lane = self.headers.get("X-Aigis-Lane", "")
        heads = {k: self.headers.get(k, "") for k in _HEADS if self.headers.get(k)}
        raw_text = (path + "\n" + "\n".join(f"{k}: {v}" for k, v in heads.items()) + "\n"
                    + body.decode("utf-8", "replace")).strip("\n")
        received_at = time.time()
        # Crudo a disco antes de cualquier análisis: un decoder que falla hoy se re-analiza mañana.
        _persist({"ts": received_at, "path": path, "ip": ip, "lane": lane, "raw": raw_text})
        threading.Thread(target=report, args=(raw_text,),
                         kwargs={"path": path, "ip": ip, "lane": lane, "received_at": received_at},
                         daemon=True).start()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = do_POST = do_PUT = _handle

    def log_message(self, fmt, *args):
        print(f"sink: {self.client_address[0]} {fmt % args}", flush=True)


def main() -> None:
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"sink del atacante en :{PORT}, reporta a {ORCH}/webhooks/attacker, log en {_log_path()}",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
