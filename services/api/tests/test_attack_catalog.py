"""Catálogo de ataques: carga bien, las rutas de archivos son seguras y un ataque del
catálogo se puede resolver a un Attack. No prueba que los payloads (huecos de opencode)
exfiltren; solo la plomería."""

from __future__ import annotations

import pytest

from aigis.attacks import injected_files, load_attacks, render
from aigis.config import REPO_ROOT
from aigis.lanes.catalog import CATALOG as LANES

CATALOG_DIR = REPO_ROOT / "attacks"
ATTACKS = load_attacks(CATALOG_DIR / "catalog.yaml")


def test_catalog_loads():
    assert ATTACKS, "el catálogo está vacío"
    assert "repo-conftest" in ATTACKS


@pytest.mark.parametrize("aid", sorted(ATTACKS))
def test_attack_shape(aid):
    a = ATTACKS[aid]
    assert a.vectors, aid
    assert a.channel, aid
    assert a.notes, aid  # cada ataque declara su hipótesis / kind / esperado
    # Resolver a un Attack con un vector válido
    atk = a.to_attack()
    assert atk.vector in a.vectors and atk.id == aid
    # Los targets son carriles que existen; none va siempre como testigo de validez
    assert a.targets and set(a.targets) <= set(LANES), (aid, a.targets)
    assert "none" in a.targets, (aid, a.targets)


# Canales que exfiltran al servidor del atacante por red: el payload DEBE llevar destino
# ({ATTACKER_URL}), si no, ni un agente obediente puede filtrar (regresión del PR #16). Los
# demás sacan el secreto por otra vía (diff entregado, git, un dominio de la allowlist, un
# archivo inyectado que corre solo), así que no necesitan el marcador.
_NEEDS_DESTINATION = {"http", "webfetch"}


@pytest.mark.parametrize("aid", sorted(ATTACKS))
def test_network_attacks_have_a_destination(aid):
    a = ATTACKS[aid]
    if a.channel not in _NEEDS_DESTINATION or a.files:
        return
    url = "http://attacker.example:9000"
    assert url in render(a.payload, url), f"{aid}: el payload no lleva {{ATTACKER_URL}}"


@pytest.mark.parametrize("aid", sorted(ATTACKS))
def test_injected_files_are_safe_and_present(aid):
    a = ATTACKS[aid]
    files = injected_files(CATALOG_DIR, a, "http://attacker.test")
    assert set(files) == set(a.files), aid
    for rel in files:
        assert not rel.startswith("/") and ".." not in rel.split("/")
        assert rel.split("/")[0] not in (".env", ".git", ".aigis", ".aigis_tests")


def test_file_injection_is_rejected_outside_repo():
    from aigis.attacks import CatalogAttack

    bad = CatalogAttack(id="x", title="x", technique="x", channel="x", vectors=["readme"],
                        files=["../.env"])
    with pytest.raises(ValueError):
        injected_files(CATALOG_DIR, bad, "http://attacker.test")
