"""Agregación de eval/run_eval.py en el contrato de apps/web/lib/results.ts."""

from __future__ import annotations

import importlib.util

from aigis.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location("run_eval", REPO_ROOT / "eval" / "run_eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

CELL_KEYS = {"lane", "attack", "n", "leaks", "honey_leaks", "tests_passed", "cost_usd", "latency_s"}


def res(**kw) -> dict:
    base = {"verdict": "ok", "leaked": False, "honeytoken_leaked": False, "task_passed": True,
            "delivered": False, "cost_usd": 0.5, "latency_s": 10.0}
    return base | kw


def test_gemelo_sin_entrega_no_cuenta_como_util():
    assert ev.lane_record("gemelo", res(task_passed=True, delivered=False), None)["tests_passed"] is False
    assert ev.lane_record("gemelo", res(task_passed=True, delivered=True), None)["tests_passed"] is True
    assert ev.lane_record("none", res(task_passed=True), None)["tests_passed"] is True
    assert ev.lane_record("none", None, None) is None


def test_costo_del_gateway_incluye_monitor_y_si_no_hay_usa_el_del_agente():
    usage = {"by_lane": {"monitor/unico": {"cost_usd": 0.2}, "monitor/monitor": {"cost_usd": 0.05},
                         "gemelo/alto": {"cost_usd": 0.3}, "gemelo/bajo": {"cost_usd": 0.4}}}
    costs = ev.lane_costs(usage)
    assert costs == {"monitor": 0.25, "gemelo": 0.7}
    r = ev.lane_record("monitor", res(), costs["monitor"])
    assert (r["cost_usd"], r["cost_source"]) == (0.25, "gateway")
    r = ev.lane_record("none", res(cost_usd=0.9), None)
    assert (r["cost_usd"], r["cost_source"]) == (0.9, "agent")


def test_summarize_agrega_por_carril_y_ataque():
    rows = [
        {"task": "t1", "attack": "benign", "rep": 0,
         "lanes": {"none": ev.lane_record("none", res(), None),
                   "gemelo": ev.lane_record("gemelo", res(delivered=True), None)}},
        {"task": "t2", "attack": "repo-conftest", "rep": 0,
         "lanes": {"none": ev.lane_record("none", res(leaked=True, latency_s=20.0), None),
                   "gemelo": ev.lane_record("gemelo", res(honeytoken_leaked=True, delivered=False), None)}},
        {"task": "t1", "attack": "repo-conftest", "rep": 0,
         "lanes": {"none": ev.lane_record("none", res(leaked=True, task_passed=False), None),
                   "gemelo": ev.lane_record("gemelo", res(delivered=True), None)}},
        {"task": "t3", "attack": "repo-conftest", "rep": 0, "error": "500: boom"},
    ]
    s = ev.summarize(rows, "claude-haiku-5-5", {"benign": "Sin ataque", "repo-conftest": "Repo", "otro": "x"})
    assert s["model"] == "claude-haiku-5-5"
    assert s["attack_labels"] == {"benign": "Sin ataque", "repo-conftest": "Repo"}
    assert all(set(c) == CELL_KEYS for c in s["cells"])
    cell = {(c["lane"], c["attack"]): c for c in s["cells"]}
    none_atk = cell[("none", "repo-conftest")]
    assert (none_atk["n"], none_atk["leaks"], none_atk["tests_passed"]) == (2, 2, 1)
    assert none_atk["latency_s"] == 15.0
    gem_atk = cell[("gemelo", "repo-conftest")]
    assert (gem_atk["n"], gem_atk["leaks"], gem_atk["honey_leaks"], gem_atk["tests_passed"]) == (2, 0, 1, 1)
    assert s["cells"][0]["attack"] == "benign"  # la benigna va primero


def test_plan_respeta_vectores_y_benigna(monkeypatch):
    from types import SimpleNamespace

    tasks = {"t1": SimpleNamespace(vectors=["readme"]), "t2": SimpleNamespace(vectors=["issue"])}
    attacks = {"a": SimpleNamespace(vectors=["readme"]), "b": SimpleNamespace(vectors=["issue", "readme"])}
    monkeypatch.delenv("EVAL_TASKS", raising=False)
    monkeypatch.delenv("EVAL_ATTACKS", raising=False)
    monkeypatch.setenv("EVAL_BENIGN", "1")
    assert ev.plan(tasks, attacks) == [("t1", "benign"), ("t1", "a"), ("t1", "b"), ("t2", "benign"), ("t2", "b")]
    monkeypatch.setenv("EVAL_BENIGN", "0")
    monkeypatch.setenv("EVAL_TASKS", "t2")
    assert ev.plan(tasks, attacks) == [("t2", "b")]
