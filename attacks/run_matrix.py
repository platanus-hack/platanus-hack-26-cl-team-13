#!/usr/bin/env python3
"""Corre TODOS los ataques del catálogo contra TODOS los carriles y vuelca la tabla de
resultados (ataque × carril -> veredicto).

No es parte de la solución: es la herramienta de validación de la demo. El criterio es el del
catálogo: un ataque sirve si `none` (sin defensa) filtra; con eso, o cae un carril del estado
del arte (ese enfoque no alcanza; si cae gemelo, es hueco nuestro) o gemelo aguanta mientras
otros caen (nuestra solución defiende).

MODO REAL (por defecto): le pega a la API desplegada, que corre el MODELO REAL (agent=claude)
en sandboxes reales (provider=remote, gVisor). Es la única forma de validar que protegemos el
modelo: el ataque tiene que vencer al modelo de verdad. Las corridas van una por una (la API
tiene una corrida a la vez) y los hits son los eventos `leak.detected` de cada corrida.

  AIGIS_MATRIX_API=http://100.100.0.9:8000 AIGIS_API_TOKEN=<token> python attacks/run_matrix.py

MODO LOCAL SIN API KEY (solo si se acaban los créditos / key, o si se pide explícitamente):
levanta una app en proceso con provider fake + agente de guion. OJO: NO prueba protección, solo
cableado — el agente de guion no sigue inyecciones y la red no se aísla. No usar por defecto.

  AIGIS_MATRIX_LOCAL=1 python attacks/run_matrix.py

Salida: imprime la tabla y la guarda en attacks/results/matrix.md y attacks/results/matrix.json.
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent            # .../attacks
API_DIR = HERE.parent / "services" / "api"        # .../services/api
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(HERE.parent / "services"))  # bucket del atacante (attacker.sink)

import httpx  # noqa: E402

from aigis.attacks import load_attacks  # noqa: E402
from attacker.sink import bucket_response  # noqa: E402

DEFAULT_LANES = ["none", "monitor", "fides", "gemelo"]
TASK_ID = os.environ.get("AIGIS_MATRIX_TASK", "mask-keys")
LANES = [x for x in os.environ.get("AIGIS_MATRIX_LANES", ",".join(DEFAULT_LANES)).split(",") if x]
ONLY = [x for x in os.environ.get("AIGIS_MATRIX_ONLY", "").split(",") if x]  # subset de ataques
LOCAL = os.environ.get("AIGIS_MATRIX_LOCAL") == "1"
API = os.environ.get("AIGIS_MATRIX_API", "http://100.100.0.9:8000").rstrip("/")
TOKEN = os.environ.get("AIGIS_API_TOKEN", "")
RUN_TIMEOUT_S = float(os.environ.get("AIGIS_MATRIX_RUN_TIMEOUT", "1200"))
SECRET = "matrix-secret"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_attacker(port: int, orch_url: str, hits: list[bytes]) -> http.server.HTTPServer:
    """Atacante local (solo modo local): reenvía todo, firmado, al webhook del orquestador.
    También sirve el bucket de paquetes, como el sink real."""
    class H(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            if self.command == "GET":  # los GET al bucket descargan paquetes, no son exfiltración
                resp = bucket_response(self.path)
                if resp is not None:
                    code, body, ctype = resp
                    self.send_response(code)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            n = int(self.headers.get("Content-Length") or 0)
            raw = (self.path + "\n").encode() + (self.rfile.read(n) if n else b"")
            hits.append(raw)
            body = json.dumps({"raw": raw.decode("utf-8", "replace"), "channel": "http",
                               "received_at": time.time()}).encode()
            sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
            try:
                httpx.post(f"{orch_url}/webhooks/attacker", content=body,
                           headers={"X-Aigis-Signature": sig, "Content-Type": "application/json"}, timeout=5)
            except Exception:
                pass
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        do_GET = do_POST = _handle

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def wait_run(c: httpx.Client, run_id: str, timeout: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/runs/{run_id}")
        r.raise_for_status()
        run = r.json()
        if run["status"] in ("done", "failed", "cancelled"):
            return run
        time.sleep(2)
    raise TimeoutError(run_id)


def leak_events(c: httpx.Client, run_id: str) -> int:
    """Cuenta los leak.detected de una corrida terminada (SSE sin follow)."""
    n = 0
    with c.stream("GET", f"/runs/{run_id}/events", params={"follow": "false"}, timeout=60) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line == "event: leak.detected":
                n += 1
    return n


def fmt_cell(res: dict | None) -> str:
    if not res:
        return "—"
    v = res.get("verdict", "?")
    marks = []
    if res.get("leaked"):
        marks.append("LEAK")
    if res.get("honeytoken_leaked"):
        marks.append("hon")
    if res.get("network_cut"):
        marks.append("netcut")
    if res.get("denied_tools"):
        marks.append(f"deny{res['denied_tools']}")
    return v + (f" ({'/'.join(marks)})" if marks else "")


def run_one(c: httpx.Client, task_id: str, attack_id: str | None, lanes: list[str],
            timeout: float = RUN_TIMEOUT_S, ablate: list[str] | None = None) -> dict:
    """Lanza una corrida y espera su fin. attack_id=None = corrida benigna (sin ataque).

    Devuelve {"_run", "_status", <carril>: LaneResult | None} o {"_error": ...}.
    """
    body: dict = {"task_id": task_id, "lanes": lanes}
    if attack_id:
        body["attack_id"] = attack_id
    if ablate:
        body["ablate"] = ablate
    r = c.post("/runs", json=body)
    if r.status_code != 201:
        return {"_error": f"{r.status_code}: {r.text[:120]}", "_status_code": r.status_code}
    run_id = r.json()["run_id"]
    try:
        run = wait_run(c, run_id, timeout)
    except TimeoutError:
        return {"_error": f"timeout esperando {run_id}", "_run": run_id}
    res: dict = {ln: (run["lanes"].get(ln, {}) or {}).get("result") for ln in lanes}
    res["_run"] = run_id
    res["_status"] = run["status"]
    return res


def run_attacks(c: httpx.Client, attacks: dict, hits_of, task_id: str | None = None,
                lanes: list[str] | None = None, only: list[str] | None = None) -> dict[str, dict]:
    task_id = task_id or TASK_ID
    lanes = lanes or LANES
    only = ONLY if only is None else only
    rows: dict[str, dict] = {}
    for aid in attacks:
        if only and aid not in only:
            continue
        res = run_one(c, task_id, aid, lanes)
        if res.get("_error"):
            rows[aid] = res
            print(f"{aid}: ERROR {res['_error']}", flush=True)
            continue
        res["_hits"] = hits_of(res["_run"])
        res["_kind"] = "code" if attacks[aid].files else "model"
        rows[aid] = res
        cells = "  ".join(f"{ln}={fmt_cell(res.get(ln))}" for ln in lanes)
        print(f"{aid:20} [{res['_kind']:5}] {res['_run']} hits={res['_hits']}  {cells}", flush=True)
    return rows


@contextmanager
def real_client() -> Iterator[tuple[httpx.Client, dict]]:
    """Cliente contra la API desplegada (modelo real). Falla si la API no corre agent=claude."""
    if not TOKEN:
        raise SystemExit("falta AIGIS_API_TOKEN para la API desplegada")
    with httpx.Client(base_url=API, timeout=30, headers={"authorization": f"Bearer {TOKEN}"}) as c:
        h = c.get("/health").json()
        if h.get("agent") != "claude":
            raise SystemExit(f"la API no corre el modelo real: {h}")
        yield c, {"api": API, "provider": h.get("provider"), "agent": h.get("agent"), "model": h.get("model")}


@contextmanager
def local_client() -> Iterator[tuple[httpx.Client, dict]]:
    """App en proceso con provider fake + agente de guion. Solo prueba cableado, no protección."""
    import uvicorn

    from aigis.app import create_app
    from aigis.config import REPO_ROOT, Settings
    from aigis.gateway_client import StubGateway
    from aigis.providers.fake import FakeProvider
    from aigis.store import MemoryStore

    port, aport = free_port(), free_port()
    boxes = Path(os.environ.get("TEMP", "/tmp")) / f"aigis-matrix-{port}"
    settings = Settings(
        sandbox_provider="fake", public_host="127.0.0.1", port=port, gateway_stub=True,
        gateway_url_sandbox=f"http://127.0.0.1:{port}/gw", attacker_url_sandbox=f"http://127.0.0.1:{aport}",
        agent="scripted", leak_grace_s=1.0, high_grace_after_low_s=10, agent_timeout_s=120, test_timeout_s=120,
        tasks_dir=REPO_ROOT / "tasks", sandbox_dir=REPO_ROOT / "sandbox", webhook_secret=SECRET,
    )
    provider = FakeProvider(root=boxes, gateway_hosts=(f"127.0.0.1:{port}",))
    app = create_app(settings, provider=provider, gateway=StubGateway(), store=MemoryStore())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    hits: list[bytes] = []
    atk = start_attacker(aport, f"http://127.0.0.1:{port}", hits)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as c:
            yield c, {"api": "local", "provider": "fake", "agent": "scripted", "model": settings.model}
    finally:
        atk.shutdown()
        server.should_exit = True
        th.join(timeout=10)


def main_real(attacks: dict) -> tuple[dict, dict]:
    with real_client() as (c, meta):
        print(f"task={TASK_ID} api={API} provider={meta['provider']} agent={meta['agent']} lanes={LANES}\n",
              flush=True)
        rows = run_attacks(c, attacks, lambda run_id: leak_events(c, run_id))
    return meta, rows


def main_local(attacks: dict) -> tuple[dict, dict]:
    with local_client() as (c, meta):
        print(f"task={TASK_ID} provider=fake agent=scripted lanes={LANES} (MODO LOCAL: no prueba protección)\n")
        rows = run_attacks(c, attacks, lambda run_id: leak_events(c, run_id))
    return meta, rows


def write_results(meta: dict, rows: dict) -> None:
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "matrix.json").write_text(json.dumps(
        {"task": TASK_ID, **meta, "lanes": LANES, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
         "rows": rows}, indent=2, ensure_ascii=False) + "\n", "utf-8")

    lines = ["# Matriz de resultados — ataque × carril", "",
             f"`task={TASK_ID}` · `provider={meta['provider']}` · `agent={meta['agent']}` · "
             f"generada {time.strftime('%Y-%m-%d %H:%M')}", "",
             "| ataque | kind | hits | " + " | ".join(LANES) + " |",
             "|---|---|---|" + "---|" * len(LANES)]
    for aid, res in rows.items():
        if res.get("_error"):
            lines.append(f"| {aid} | | | {res['_error']} |" + " |" * (len(LANES) - 1))
            continue
        cells = " | ".join(fmt_cell(res.get(ln)) for ln in LANES)
        lines.append(f"| {aid} | {res['_kind']} | {res['_hits']} | {cells} |")
    lines += ["", "Leyenda: `LEAK`=filtró secreto real · `hon`=solo honeytoken · `netcut`=red cortada · "
              "`denyN`=N herramientas negadas · hits=eventos `leak.detected` de la corrida. "
              "gemelo: `delivered`=no filtró y la tarea pasó."]
    if meta["agent"] != "claude":
        lines += ["", "OJO: corrida con agente de guion. Los ataques `model` no caen solos y la red no se "
                  "aísla; no mide protección."]
    (out / "matrix.md").write_text("\n".join(lines) + "\n", "utf-8")
    print(f"\nGuardado: {out / 'matrix.md'}  y  {out / 'matrix.json'}")


def main() -> int:
    attacks = load_attacks(HERE / "catalog.yaml")
    meta, rows = main_local(attacks) if LOCAL else main_real(attacks)
    write_results(meta, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
