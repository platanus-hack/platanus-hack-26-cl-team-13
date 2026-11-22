#!/usr/bin/env python3
"""Prueba de esfuerzo de la matriz de ataques contra la API desplegada (modelo real).

Por oleadas: en cada nivel de AIGIS_STRESS_LEVELS (por defecto 1,5,10,20) manda N corridas a
la vez (ataques del catálogo en round-robin, todos los carriles) y espera a que terminen.
Mide por corrida: latencia del POST, espera en cola, duración, estado final y veredictos; y por
oleada: errores HTTP, corridas failed/timeout, latencia de /health bajo carga y regresiones
contra la línea base (attacks/results/matrix.json): un carril que cambia de veredicto, y sobre
todo gemelo filtrando (eso es un hueco, no ruido).

  AIGIS_API_TOKEN=<token> python attacks/stress_matrix.py

Variables: AIGIS_MATRIX_API (http://100.100.0.9:8000), AIGIS_STRESS_LEVELS (1,5,10,20),
AIGIS_MATRIX_LANES, AIGIS_MATRIX_ONLY, AIGIS_STRESS_WAVE_TIMEOUT (s, por oleada, 14400),
AIGIS_STRESS_MAX_FAIL (fracción de corridas falladas que corta la rampa, 0.5).

Ctrl+C cancela las corridas que siguen en vuelo para no seguir gastando API.
Salida: attacks/results/stress.md y attacks/results/stress.json.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "services" / "api"))

import httpx  # noqa: E402

from aigis.attacks import load_attacks  # noqa: E402

API = os.environ.get("AIGIS_MATRIX_API", "http://100.100.0.9:8000").rstrip("/")
TOKEN = os.environ.get("AIGIS_API_TOKEN", "")
TASK_ID = os.environ.get("AIGIS_MATRIX_TASK", "mask-keys")
LANES = [x for x in os.environ.get("AIGIS_MATRIX_LANES", "none,monitor,fides,gemelo").split(",") if x]
ONLY = [x for x in os.environ.get("AIGIS_MATRIX_ONLY", "").split(",") if x]
LEVELS = [int(x) for x in os.environ.get("AIGIS_STRESS_LEVELS", "1,5,10,20").split(",") if x]
WAVE_TIMEOUT_S = float(os.environ.get("AIGIS_STRESS_WAVE_TIMEOUT", "14400"))
MAX_FAIL = float(os.environ.get("AIGIS_STRESS_MAX_FAIL", "0.5"))
POLL_S = 5.0
TERMINAL = ("done", "failed", "cancelled")


def ts(s: str | None) -> float | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def verdicts(run: dict) -> dict[str, dict | None]:
    return {ln: (run["lanes"].get(ln) or {}).get("result") for ln in LANES}


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def health_probe(c: httpx.Client, stop: threading.Event, out: list[float], errs: list[str]) -> None:
    while not stop.is_set():
        t0 = time.time()
        try:
            c.get("/health", timeout=15).raise_for_status()
            out.append(time.time() - t0)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{type(e).__name__}: {e}"[:160])
        stop.wait(10)


def run_wave(c: httpx.Client, n: int, attack_ids: list[str], offset: int, baseline: dict) -> dict:
    print(f"\n=== oleada n={n} ===", flush=True)
    runs: dict[str, dict] = {}
    post_errors: list[str] = []
    wave_t0 = time.time()

    for i in range(n):
        aid = attack_ids[(offset + i) % len(attack_ids)]
        t0 = time.time()
        try:
            r = c.post("/runs", json={"task_id": TASK_ID, "attack_id": aid, "lanes": LANES})
        except Exception as e:  # noqa: BLE001
            post_errors.append(f"{aid}: {type(e).__name__}: {e}"[:200])
            continue
        lat = time.time() - t0
        if r.status_code != 201:
            post_errors.append(f"{aid}: {r.status_code} {r.text[:120]}")
            continue
        rid = r.json()["run_id"]
        runs[rid] = {"attack": aid, "post_s": lat, "submitted": t0, "dequeued": None, "status": "queued"}
    print(f"enviadas {len(runs)}/{n}, errores POST={len(post_errors)}", flush=True)

    h_lat: list[float] = []
    h_err: list[str] = []
    stop = threading.Event()
    th = threading.Thread(target=health_probe, args=(c, stop, h_lat, h_err), daemon=True)
    th.start()
    poll_errors = 0
    try:
        while time.time() - wave_t0 < WAVE_TIMEOUT_S:
            pending = [rid for rid, x in runs.items() if x["status"] not in TERMINAL]
            if not pending:
                break
            for rid in pending:
                try:
                    r = c.get(f"/runs/{rid}")
                    r.raise_for_status()
                except Exception:  # noqa: BLE001
                    poll_errors += 1
                    continue
                run = r.json()
                x = runs[rid]
                if x["dequeued"] is None and run["status"] != "queued":
                    x["dequeued"] = time.time()
                if run["status"] in TERMINAL and x["status"] not in TERMINAL:
                    x.update(status=run["status"], error=run.get("error"), finished=time.time(),
                             created_at=ts(run.get("created_at")), ended_at=ts(run.get("ended_at")),
                             lanes=verdicts(run))
                    print(f"  {rid} {x['attack']:20} {run['status']:9} "
                          f"{x['finished'] - x['submitted']:.0f}s", flush=True)
                else:
                    x["status"] = run["status"]
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\nCtrl+C: cancelando corridas en vuelo...", flush=True)
        for rid, x in runs.items():
            if x["status"] not in TERMINAL:
                try:
                    c.post(f"/runs/{rid}/cancel")
                except Exception:  # noqa: BLE001
                    pass
        stop.set()
        raise
    finally:
        stop.set()
        th.join(timeout=20)

    timeouts = [rid for rid, x in runs.items() if x["status"] not in TERMINAL]
    for rid in timeouts:
        try:
            c.post(f"/runs/{rid}/cancel")
        except Exception:  # noqa: BLE001
            pass

    done = [x for x in runs.values() if x["status"] == "done"]
    failed = [x for x in runs.values() if x["status"] in ("failed", "cancelled")]
    queue_wait = [x["dequeued"] - x["submitted"] for x in runs.values() if x.get("dequeued")]
    exec_s = [x["finished"] - x["dequeued"] for x in done if x.get("dequeued")]

    regressions: list[str] = []
    gemelo_leaks: list[str] = []
    for rid, x in runs.items():
        if x["status"] != "done":
            continue
        base = (baseline.get(x["attack"]) or {})
        for ln, res in (x.get("lanes") or {}).items():
            if not res:
                continue
            if ln == "gemelo" and res.get("leaked"):
                gemelo_leaks.append(f"{rid} {x['attack']}")
            b = base.get(ln) or {}
            if b and (b.get("verdict"), bool(b.get("leaked"))) != (res.get("verdict"), bool(res.get("leaked"))):
                regressions.append(f"{rid} {x['attack']} {ln}: {b.get('verdict')}->{res.get('verdict')}"
                                   f"{' LEAK' if res.get('leaked') else ''}")

    summary = {
        "n": n, "submitted": len(runs), "post_errors": post_errors, "poll_errors": poll_errors,
        "done": len(done), "failed": len(failed), "timeouts": len(timeouts),
        "errors": sorted({str(x.get("error"))[:160] for x in failed if x.get("error")}),
        "wall_s": time.time() - wave_t0,
        "post_p50_s": pct([x["post_s"] for x in runs.values()], 0.5),
        "queue_p50_s": pct(queue_wait, 0.5), "queue_max_s": max(queue_wait, default=None),
        "exec_p50_s": pct(exec_s, 0.5), "exec_p95_s": pct(exec_s, 0.95),
        "health_p50_s": pct(h_lat, 0.5), "health_max_s": max(h_lat, default=None),
        "health_errors": h_err, "regressions": regressions, "gemelo_leaks": gemelo_leaks,
        "runs": runs,
    }
    print(f"oleada n={n}: done={len(done)} failed={len(failed)} timeout={len(timeouts)} "
          f"wall={summary['wall_s']:.0f}s cola_max={summary['queue_max_s']} "
          f"regresiones={len(regressions)} gemelo_leaks={len(gemelo_leaks)}", flush=True)
    return summary


def f(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}"


def write(meta: dict, waves: list[dict]) -> None:
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "stress.json").write_text(json.dumps({**meta, "waves": waves}, indent=2, ensure_ascii=False,
                                                default=str) + "\n", "utf-8")
    L = ["# Prueba de esfuerzo — matriz de ataques", "",
         f"`api={meta['api']}` · `provider={meta['provider']}` · `agent={meta['agent']}` · "
         f"`lanes={','.join(LANES)}` · {meta['started']}", "",
         "| n | done | failed | timeout | err POST | wall s | cola p50/max s | ejec p50/p95 s | "
         "/health p50/max s | regresiones | gemelo LEAK |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in waves:
        L.append(f"| {w['n']} | {w['done']} | {w['failed']} | {w['timeouts']} | {len(w['post_errors'])} | "
                 f"{w['wall_s']:.0f} | {f(w['queue_p50_s'])}/{f(w['queue_max_s'])} | "
                 f"{f(w['exec_p50_s'])}/{f(w['exec_p95_s'])} | {f(w['health_p50_s'])}/{f(w['health_max_s'])} | "
                 f"{len(w['regressions'])} | {len(w['gemelo_leaks'])} |")
    for w in waves:
        notes = ([f"- error: {e}" for e in w["errors"] + w["post_errors"] + w["health_errors"][:5]]
                 + [f"- regresión: {r}" for r in w["regressions"]]
                 + [f"- **gemelo filtró**: {g}" for g in w["gemelo_leaks"]])
        if notes:
            L += ["", f"## n={w['n']}", *notes]
    (out / "stress.md").write_text("\n".join(L) + "\n", "utf-8")
    print(f"\nGuardado: {out / 'stress.md'} y {out / 'stress.json'}")


def main() -> int:
    if not TOKEN:
        raise SystemExit("falta AIGIS_API_TOKEN")
    attacks = load_attacks(HERE / "catalog.yaml")
    attack_ids = [a for a in attacks if not ONLY or a in ONLY]
    base_path = HERE / "results" / "matrix.json"
    baseline = json.loads(base_path.read_text("utf-8"))["rows"] if base_path.exists() else {}
    waves: list[dict] = []
    with httpx.Client(base_url=API, timeout=30, headers={"authorization": f"Bearer {TOKEN}"}) as c:
        h = c.get("/health").json()
        if h.get("agent") != "claude":
            raise SystemExit(f"la API no corre el modelo real: {h}")
        meta = {"api": API, "provider": h.get("provider"), "agent": h.get("agent"),
                "started": time.strftime("%Y-%m-%d %H:%M"), "levels": LEVELS}
        print(f"api={API} provider={meta['provider']} agent=claude niveles={LEVELS} "
              f"ataques={len(attack_ids)} corridas totales={sum(LEVELS)}", flush=True)
        offset = 0
        try:
            for n in LEVELS:
                w = run_wave(c, n, attack_ids, offset, baseline)
                offset += n
                waves.append(w)
                write(meta, waves)
                bad = w["failed"] + w["timeouts"] + len(w["post_errors"])
                if n and bad / n > MAX_FAIL:
                    print(f"corto la rampa: {bad}/{n} corridas malas en n={n}", flush=True)
                    break
        except KeyboardInterrupt:
            write(meta, waves)
            return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
