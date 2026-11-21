"""Catálogo de tareas: cada tarea carga, trae tests y su guion resuelve la tarea sin ataque."""

from __future__ import annotations

import pytest

from aigis.config import REPO_ROOT
from aigis.tasks import load_tasks

TASKS = load_tasks(REPO_ROOT / "tasks")


def test_catalog_shape():
    assert len(TASKS) >= 5
    for t in TASKS.values():
        assert t.tests_dir.is_dir() and any(t.tests_dir.glob("test_*.py")), t.id
        assert t.secret_spec(), t.id
        assert "{payload}" in t.doc_page() and "{payload}" in t.issue_template(), t.id
        assert t.script("default"), t.id


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_clean_run_delivers(harness, task_id):
    with harness.client() as c:
        r = c.post("/runs", json={"task_id": task_id, "lanes": ["none", "gemelo"]})
        assert r.status_code == 201, r.text
        run_id = r.json()["run_id"]
    run = harness.wait_run(run_id)
    assert run["status"] == "done", run
    res = {k: v["result"] for k, v in run["lanes"].items()}
    assert res["none"]["task_passed"], res["none"]
    if task_id != "mask-keys":  # el guion de mask-keys imita a un agente ya engañado
        assert not res["none"]["leaked"], res["none"]
    assert res["gemelo"]["delivered"], res["gemelo"]
