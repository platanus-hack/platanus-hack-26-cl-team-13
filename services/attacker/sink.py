"""Sink publico que recibe exfiltraciones y sirve el bucket de paquetes.

Hace de servidor del atacante: acepta cualquier GET o POST, guarda lo recibido y lo
reenvía firmado (HMAC-SHA256 con AIGIS_WEBHOOK_SECRET) a /webhooks/attacker del
orquestador, que busca ahí los secretos de la corrida y atribuye la filtración.

Además sirve el bucket de dependencias internas (pre-condición del ataque
supply-chain `bucket-supply-chain`): los GET bajo /bucket/ descargan paquetes y NO
se reportan como exfiltración (descargar un paquete no filtra nada); el resto de
rutas y métodos se reporta igual que antes. El bucket no se sube por corrida: su
contenido vive en services/attacker/bucket/<paquete>/.

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
from pathlib import Path

PORT = int(os.environ.get("ATTACKER_PORT", "9000"))
ORCH = os.environ.get("AIGIS_ORCH_URL", "http://127.0.0.1:8000").rstrip("/")
SECRET = os.environ.get("AIGIS_WEBHOOK_SECRET", "dev-webhook-secret")
MAX_BODY = 1 << 20
BUCKET_DIR = Path(__file__).resolve().parent / "bucket"


def bucket_response(path: str) -> tuple[int, bytes, str] | None:
    """Respuesta para un GET /bucket/..., o None si la ruta no es del bucket.

    Mini-registry: GET /bucket/<paquete>.json devuelve la metadata (package.json
    más la lista de archivos) y GET /bucket/<paquete>/<archivo> devuelve el archivo.
    Lo usan también los stubs de atacante de los tests y de la matriz local, para
    que el bucket se sirva igual en todos los ambientes.
    """
    if not path.startswith("/bucket/"):
        return None
    rest = path[len("/bucket/"):].split("?", 1)[0].strip("/")
    if rest.endswith(".json"):  # metadata: /bucket/<paquete>.json
        pkg, fname = rest[: -len(".json")], ""
    else:
        pkg, _, fname = rest.partition("/")
    if not pkg or ".." in rest.split("/") or not (BUCKET_DIR / pkg).is_dir():
        return 404, b"no such package\n", "text/plain"
    if not fname:
        meta_p = BUCKET_DIR / pkg / "package.json"
        if not meta_p.is_file():
            return 404, b"no metadata\n", "text/plain"
        meta = json.loads(meta_p.read_text("utf-8"))
        meta["files"] = sorted(p.name for p in (BUCKET_DIR / pkg).iterdir()
                               if p.is_file() and p.name != "package.json" and not p.name.startswith("."))
        return 200, json.dumps(meta).encode() + b"\n", "application/json"
    f = BUCKET_DIR / pkg / fname
    if "/" in fname or not f.is_file():
        return 404, b"no such file\n", "text/plain"
    return 200, f.read_bytes(), "application/octet-stream"


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
        if self.command == "GET":
            resp = bucket_response(self.path)
            if resp is not None:
                code, body, ctype = resp
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
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
    pkgs = sorted(p.name for p in BUCKET_DIR.iterdir() if p.is_dir()) if BUCKET_DIR.is_dir() else []
    print(f"sink del atacante en :{PORT}, reporta a {ORCH}/webhooks/attacker", flush=True)
    print(f"bucket de paquetes en /bucket/ : {', '.join(pkgs) or '(vacío)'}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
