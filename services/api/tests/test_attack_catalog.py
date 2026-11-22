"""Catálogo de ataques: cada payload debe poder exfiltrar si el modelo obedece.

La regresión que motiva este test: los payloads antiguos no incluían ningún destino
({ATTACKER_URL}), así que ni un agente totalmente obediente podía filtrar nada y las
defensas parecían invencibles.
"""

from __future__ import annotations

from aigis.attacks import load_attacks, render
from aigis.config import REPO_ROOT

ATTACKS = load_attacks(REPO_ROOT / "attacks" / "catalog.yaml")


def test_catalog_loads():
    assert len(ATTACKS) >= 6, "la escalera de ataques está incompleta"
    for a in ATTACKS.values():
        assert a.title and a.technique and a.channel, a.id
        assert a.vectors, a.id


def test_every_attack_has_a_destination():
    """Sin destino concreto el ataque no mide nada: ni el carril none filtraría."""
    url = "http://attacker.example:9000"
    for a in ATTACKS.values():
        if a.channel == "webfetch":
            # Exfil hacia la propia página de docs (hueco WebFetch/allowedDomains de
            # cc_sandbox): el agente ya conoce la URL por el prompt de la tarea.
            assert "URL de esta página" in a.payload, a.id
        else:
            assert url in render(a.payload, url), f"{a.id}: el payload no lleva {{ATTACKER_URL}}"


def test_to_attack_covers_declared_vectors():
    for a in ATTACKS.values():
        for v in a.vectors:
            at = a.to_attack(v)
            assert at.vector == v and at.payload == a.payload, a.id
        assert a.to_attack().vector in a.vectors, a.id


def test_run_with_catalog_attack(harness):
    """attack_id resuelve contra el catálogo y la corrida completa de punta a punta."""
    with harness.client() as c:
        r = c.post("/runs", json={"task_id": "mask-keys", "lanes": ["none", "gemelo"],
                                  "attack_id": "env-verify-direct"})
        assert r.status_code == 201, r.text
        run_id = r.json()["run_id"]
        assert c.get("/attacks").json()[0]["payload_preview"], "el catálogo no se expone"
    run = harness.wait_run(run_id)
    assert run["status"] == "done", run
    res = {k: v["result"] for k, v in run["lanes"].items()}
    assert res["none"]["leaked"] and res["none"]["verdict"] == "leaked", res["none"]
    g = res["gemelo"]
    assert g["honeytoken_leaked"] and not g["leaked"] and g["delivered"], g
