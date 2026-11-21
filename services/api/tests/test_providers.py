"""Tests de la interfaz y la fábrica de proveedores (add-sandbox-provider, grupo 2).

Escenarios: "Selección de proveedor por configuración" del spec sandbox-provider.
"""

import pytest

from gemelo.providers import (
    VALID_PROVIDERS,
    NetworkProfile,
    SandboxProvider,
    UnknownProviderError,
    gateway_only,
    get_provider,
    isolated,
    open_network,
)
from gemelo.providers.e2b import E2BProvider
from gemelo.providers.local import LocalProvider


# Scenario: Proveedor local
def test_fabrica_devuelve_proveedor_local():
    provider = get_provider({"SANDBOX_PROVIDER": "local"})
    assert isinstance(provider, LocalProvider)
    assert isinstance(provider, SandboxProvider)


def test_fabrica_devuelve_proveedor_e2b():
    assert isinstance(get_provider({"SANDBOX_PROVIDER": "e2b"}), E2BProvider)


def test_fabrica_ignora_mayusculas_y_espacios():
    assert isinstance(get_provider({"SANDBOX_PROVIDER": "  LOCAL "}), LocalProvider)


def test_fabrica_usa_local_si_no_hay_valor():
    assert isinstance(get_provider({}), LocalProvider)
    assert isinstance(get_provider({"SANDBOX_PROVIDER": ""}), LocalProvider)


# Scenario: Valor inválido
def test_fabrica_falla_con_valor_invalido_y_lista_los_validos():
    with pytest.raises(UnknownProviderError) as excinfo:
        get_provider({"SANDBOX_PROVIDER": "otro"})
    mensaje = str(excinfo.value)
    assert "otro" in mensaje
    for valido in VALID_PROVIDERS:
        assert valido in mensaje


def test_gateway_only_es_isolated_sin_allowlist():
    assert gateway_only() == isolated([])
    assert gateway_only().is_gateway_only


def test_isolated_con_allowlist_no_es_gateway_only():
    perfil = isolated(["api.example.com"])
    assert perfil.kind == "isolated"
    assert perfil.allowlist == frozenset({"api.example.com"})
    assert not perfil.is_gateway_only


def test_perfil_abierto_no_admite_allowlist():
    assert open_network().kind == "open"
    with pytest.raises(ValueError):
        NetworkProfile("open", frozenset({"api.example.com"}))
