"""Catálogo de ataques: carga bien, las rutas de archivos son seguras y un ataque del
catálogo se puede resolver a un Attack. No prueba que los payloads (huecos de opencode)
exfiltren; solo la plomería."""

from __future__ import annotations

import pytest

from aigis.attacks import injected_files, load_attacks
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
    # Los targets son carriles que existen; none es el testigo y no se lista
    assert a.targets and set(a.targets) <= set(LANES) - {"none"}, (aid, a.targets)


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
