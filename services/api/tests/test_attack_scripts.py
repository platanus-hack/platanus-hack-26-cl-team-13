"""Guion por ataque: con attack_id, el runner prefiere scripts/<attack>.json."""

from __future__ import annotations

from types import SimpleNamespace

from aigis.runner import Orchestrator


def _rc(tmp_path, attack_id: str | None):
    from aigis.tasks import Task

    t = Task(dir=tmp_path, **{"id": "t", "title": "t", "prompt": "p"})
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "default.json").write_text("{}", "utf-8")
    (tmp_path / "scripts" / "diag-runner.json").write_text("{}", "utf-8")
    (tmp_path / "scripts" / "gemelo_bajo.json").write_text("{}", "utf-8")
    run = SimpleNamespace(attack=SimpleNamespace(id=attack_id) if attack_id else None)
    rc = SimpleNamespace(task=t, run=run)
    return Orchestrator._script_for(None, rc, "gemelo", "bajo")


def test_attack_script_wins(tmp_path):
    p = _rc(tmp_path, "diag-runner")
    assert p and p.name == "diag-runner.json"


def test_lane_role_script_wins_without_attack(tmp_path):
    p = _rc(tmp_path, None)
    assert p and p.name == "gemelo_bajo.json"


def test_falls_back_to_lane_then_default(tmp_path):
    p = _rc(tmp_path, "no-existe")
    assert p and p.name == "gemelo_bajo.json"
