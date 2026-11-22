#!/usr/bin/env python3
"""Corre la evaluación por carriles y escribe la tabla de utilidad vs filtración.

Recorre tareas × (ataques del catálogo + una corrida benigna sin ataque) × repeticiones, contra
los carriles de la API, y agrega por carril × ataque en el contrato que lee la web
(`apps/web/lib/results.ts`):

    apps/web/public/results/summary.json   tabla agregada (la regenera tras cada corrida)
    results/eval-raw.jsonl                 una línea por corrida, para auditar y reanudar

Reutiliza `attacks/run_matrix.py` (cliente real, cliente local y `run_one`).

MODO REAL (por defecto): API desplegada con el modelo real.

    AIGIS_MATRIX_API=https://... AIGIS_API_TOKEN=<token> EVAL_MAX_USD=10 python eval/run_eval.py

MODO LOCAL: provider fake + agente de guion. Prueba el cableado, no la protección.

    AIGIS_EVAL_LOCAL=1 python eval/run_eval.py

Variables:
    EVAL_TASKS     tareas separadas por coma (por defecto: todas)
    EVAL_ATTACKS   ataques separados por coma (por defecto: todo el catálogo)
    EVAL_BENIGN    1 (defecto) agrega la corrida sin ataque, que mide utilidad
    EVAL_REPEATS   repeticiones por combinación (defecto 1). Claude no se siembra.
    EVAL_LANES     carriles (defecto: los de la matriz)
    EVAL_MAX_USD   tope de gasto de esta eval (defecto 10). Se detiene antes de pasarlo.
    EVAL_MODEL     modelo a declarar si la API no lo informa en /health

Flags: --resume salta las combinaciones que ya están en eval-raw.jsonl.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "attacks"))           # run_matrix no es un paquete
sys.path.insert(0, str(ROOT / "services" / "api"))

BENIGN = "benign"
RAW = ROOT / "results" / "eval-raw.jsonl"
SUMMARY = ROOT / "apps" / "web" / "public" / "results" / "summary.json"


def env_list(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


# ---------- agregación (pura, testeada en services/api/tests/test_eval_summary.py) ----------

def lane_costs(usage: dict | None) -> dict[str, float]:
    """Suma el uso del gateway por carril. Claves: "<carril>/<rol>" y "<carril>/monitor"."""
    out: dict[str, float] = {}
    for key, u in ((usage or {}).get("by_lane") or {}).items():
        lane = key.split("/", 1)[0]
        out[lane] = out.get(lane, 0.0) + float((u or {}).get("cost_usd") or 0.0)
    return out


def lane_record(lane: str, result: dict | None, gw_cost: float | None) -> dict | None:
    """Lo que se guarda por carril de una corrida. None si el carril no tiene resultado."""
    if not result:
        return None
    passed = bool(result.get("task_passed"))
    if lane == "gemelo":
        # Si el gemelo no entregó el diff, la utilidad es cero aunque pasen los tests
        passed = passed and bool(result.get("delivered"))
    cost, source = (gw_cost, "gateway") if gw_cost is not None else (float(result.get("cost_usd") or 0.0), "agent")
    return {"verdict": result.get("verdict"), "leaked": bool(result.get("leaked")),
            "honeytoken_leaked": bool(result.get("honeytoken_leaked")), "tests_passed": passed,
            "cost_usd": round(cost, 6), "cost_source": source,
            "latency_s": float(result.get("latency_s") or 0.0)}


def summarize(rows: Iterable[dict], model: str, labels: dict[str, str]) -> dict:
    cells: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row.get("error"):
            continue
        for lane, rec in (row.get("lanes") or {}).items():
            if not rec:
                continue
            c = cells.setdefault((lane, row["attack"]), {
                "lane": lane, "attack": row["attack"], "n": 0, "leaks": 0, "honey_leaks": 0,
                "tests_passed": 0, "_cost": 0.0, "_lat": 0.0})
            c["n"] += 1
            c["leaks"] += rec["leaked"]
            c["honey_leaks"] += rec["honeytoken_leaked"]
            c["tests_passed"] += rec["tests_passed"]
            c["_cost"] += rec["cost_usd"]
            c["_lat"] += rec["latency_s"]
    out = []
    for c in cells.values():
        n = c["n"]
        out.append({k: v for k, v in c.items() if not k.startswith("_")}
                   | {"cost_usd": round(c["_cost"] / n, 4), "latency_s": round(c["_lat"] / n, 1)})
    out.sort(key=lambda c: (c["attack"] != BENIGN, c["attack"], c["lane"]))
    used = {c["attack"] for c in out}
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": model,
            "attack_labels": {k: v for k, v in labels.items() if k in used}, "cells": out}


# ---------- ejecución ----------

def load_raw() -> list[dict]:
    if not RAW.exists():
        return []
    return [json.loads(line) for line in RAW.read_text("utf-8").splitlines() if line.strip()]


def write_summary(rows: list[dict], model: str, labels: dict[str, str]) -> None:
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summarize(rows, model, labels), indent=2, ensure_ascii=False) + "\n", "utf-8")


def plan(tasks: dict, attacks: dict) -> list[tuple[str, str]]:
    """Combinaciones (tarea, ataque) compatibles: el ataque comparte un vector con la tarea."""
    task_ids = env_list("EVAL_TASKS") or sorted(tasks)
    attack_ids = env_list("EVAL_ATTACKS") or list(attacks)
    combos: list[tuple[str, str]] = []
    for t in task_ids:
        if t not in tasks:
            raise SystemExit(f"tarea desconocida: {t}")
        if os.environ.get("EVAL_BENIGN", "1") == "1":
            combos.append((t, BENIGN))
        for a in attack_ids:
            if a not in attacks:
                raise SystemExit(f"ataque desconocido: {a}")
            if set(attacks[a].vectors) & set(tasks[t].vectors):
                combos.append((t, a))
    return combos


def main() -> int:
    import httpx
    import run_matrix as rm

    from aigis.attacks import load_attacks
    from aigis.tasks import load_tasks

    attacks = load_attacks(ROOT / "attacks" / "catalog.yaml")
    tasks = load_tasks(ROOT / "tasks")
    labels = {BENIGN: "Sin ataque (utilidad)"} | {a.id: a.title for a in attacks.values()}
    lanes = env_list("EVAL_LANES") or rm.LANES
    repeats = int(os.environ.get("EVAL_REPEATS", "1"))
    max_usd = float(os.environ.get("EVAL_MAX_USD", "10"))
    local = os.environ.get("AIGIS_EVAL_LOCAL") == "1"

    rows = load_raw() if "--resume" in sys.argv else []
    if "--resume" not in sys.argv and RAW.exists():
        RAW.rename(RAW.with_suffix(f".{int(time.time())}.jsonl"))  # no se pisa una eval anterior
    done = {(r["task"], r["attack"], r["rep"]) for r in rows if not r.get("error")}
    spent = sum(rec["cost_usd"] for r in rows for rec in (r.get("lanes") or {}).values() if rec)

    combos = [(t, a, rep) for t, a in plan(tasks, attacks) for rep in range(repeats)]
    todo = [c for c in combos if c not in done]
    print(f"eval: {len(combos)} combinaciones, {len(todo)} pendientes, carriles={lanes}, "
          f"tope USD {max_usd:.2f} (gastado {spent:.2f})", flush=True)

    RAW.parent.mkdir(parents=True, exist_ok=True)
    with (rm.local_client() if local else rm.real_client()) as (c, meta):
        model = os.environ.get("EVAL_MODEL") or meta.get("model") or "claude-haiku-5-5"
        if local:  # visible en /resultados: estos datos no miden protección
            model = f"{model} · LOCAL agente de guion (no mide protección)"
        for i, (task_id, attack, rep) in enumerate(todo, 1):
            reserve = 2.5
            try:
                b = c.get("/budget")
                if b.status_code == 200:
                    bj = b.json()
                    reserve = float(bj.get("reserved_per_run_usd") or reserve)
                    if not bj.get("live_enabled", True):
                        print("corte global de presupuesto activo: se detiene la eval", flush=True)
                        break
            except httpx.HTTPError:
                pass
            if spent + reserve > max_usd:
                print(f"se detiene: gastado {spent:.2f} + reserva {reserve:.2f} > tope {max_usd:.2f}", flush=True)
                break

            res = rm.run_one(c, task_id, None if attack == BENIGN else attack, lanes)
            row: dict = {"task": task_id, "attack": attack, "rep": rep, "run_id": res.get("_run"),
                         "status": res.get("_status"), "ts": time.time()}
            if res.get("_error"):
                row["error"] = res["_error"]
                if res.get("_status_code") == 429:
                    print(f"[{i}/{len(todo)}] 429: {res['_error']} — se detiene", flush=True)
                    break
            else:
                usage = None
                try:
                    u = c.get(f"/runs/{res['_run']}/usage")
                    usage = u.json() if u.status_code == 200 else None
                except httpx.HTTPError:
                    pass
                costs = lane_costs(usage) if usage else {}
                row["lanes"] = {ln: lane_record(ln, res.get(ln), costs.get(ln) if usage else None) for ln in lanes}
                spent += sum(rec["cost_usd"] for rec in row["lanes"].values() if rec)
            with RAW.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
            write_summary(rows, model, labels)
            verdicts = " ".join(f"{ln}={(rec or {}).get('verdict')}" for ln, rec in (row.get("lanes") or {}).items())
            print(f"[{i}/{len(todo)}] {task_id} × {attack} #{rep} {row.get('run_id')} "
                  f"{row.get('error') or verdicts}  (gastado {spent:.2f})", flush=True)
        write_summary(rows, model, labels)
    print(f"\nGuardado: {SUMMARY}  y  {RAW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
