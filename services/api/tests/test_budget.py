"""Corte global de presupuesto: gasto real de aigis_usage más reserva por corrida sin terminar."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aigis.config import Settings
from aigis.runner import Orchestrator
from aigis.store import MemoryStore


def _budget(store: MemoryStore, statuses: list[str], **kw) -> dict:
    settings = Settings(run_budget_usd=kw.pop("run_budget_usd", 2.5), **kw)
    contexts = {f"r{i}": SimpleNamespace(run=SimpleNamespace(status=st)) for i, st in enumerate(statuses)}
    fake = SimpleNamespace(settings=settings, store=store, contexts=contexts)
    return asyncio.run(Orchestrator.budget(fake))


def _store(*costs: float) -> MemoryStore:
    st = MemoryStore()
    for i, c in enumerate(costs):
        st.usage[f"done{i}"] = {"cost_usd": c, "by_lane": {}}
    return st


def test_sin_presupuesto_no_hay_corte():
    b = _budget(_store(100.0), ["running"] * 5, budget_usd=0)
    assert b["live_enabled"] is True


def test_corrida_terminada_solo_suma_su_gasto_real():
    b = _budget(_store(1.0, 2.0), ["done", "failed", "cancelled"], budget_usd=100)
    assert b["spent_usd"] == 3.0
    assert b["in_flight"] == 0
    assert b["committed_usd"] == 3.0
    assert b["runs_counted"] == 2


def test_corridas_activas_y_en_cola_quedan_reservadas():
    b = _budget(_store(1.0), ["queued", "running", "evaluating", "done"], budget_usd=100)
    assert b["in_flight"] == 3
    assert b["committed_usd"] == 1.0 + 3 * 2.5


def test_corte_al_90_por_ciento():
    # límite 9.0: 5.0 gastado + 1 activa (2.5) = 7.5; una nueva llevaría a 10.0 > 9.0
    assert _budget(_store(5.0), ["running"], budget_usd=10)["live_enabled"] is False
    # 4.0 + 2.5 de la nueva = 6.5 <= 9.0
    assert _budget(_store(4.0), [], budget_usd=10)["live_enabled"] is True


def test_post_runs_responde_429_budget_y_budget_no_filtra_secretos(harness):
    harness.settings.budget_usd = 0.01
    with harness.client() as c:
        r = c.post("/runs", json={"task_id": "mask-keys"})
        assert r.status_code == 429
        assert r.json()["error"] == "budget"
        b = c.get("/budget")
        assert b.status_code == 200
        body = b.text.lower()
        for needle in ("token", "key", "secret", "sk-"):
            assert needle not in body
        assert b.json()["live_enabled"] is False


def test_usage_de_una_corrida(harness):
    with harness.client() as c:
        run_id = c.post("/runs", json={"task_id": "mask-keys", "lanes": ["none"]}).json()["run_id"]
        harness.wait_run(run_id)
        harness.store.usage[run_id] = {"cost_usd": 0.12, "requests": 3, "token_hash": "x",
                                       "by_lane": {"none/unico": {"cost_usd": 0.12}}}
        u = c.get(f"/runs/{run_id}/usage").json()
        assert u["cost_usd"] == 0.12
        assert u["by_lane"] == {"none/unico": {"cost_usd": 0.12}}
        assert "token_hash" not in u
        assert c.get("/runs/nada/usage").status_code == 404
