"""Plantilla E2B versionada por el contenido de sandbox/. Sin red ni E2B_API_KEY."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aigis.providers import e2b as e2b_provider
from aigis.providers import e2b_template
from aigis.providers.e2b import TEMPLATE_PREFIX, sandbox_digest, template_name

REPO_SANDBOX = Path(__file__).resolve().parents[3] / "sandbox"


@pytest.fixture(autouse=True)
def _sin_override(monkeypatch):
    monkeypatch.delenv("E2B_TEMPLATE", raising=False)


def _ctx(tmp_path: Path) -> Path:
    (tmp_path / "hooks").mkdir(parents=True)
    (tmp_path / "Dockerfile").write_bytes(b"FROM python:3.12-slim\nCOPY hooks/ /opt/aigis/hooks/\n")
    (tmp_path / "hooks" / "hook.py").write_bytes(b"print('hook')\n")
    return tmp_path


def test_nombre_con_prefijo_y_hash(tmp_path):
    name = template_name(_ctx(tmp_path))
    assert name.startswith(f"{TEMPLATE_PREFIX}-")
    assert len(name) == len(TEMPLATE_PREFIX) + 1 + 12


def test_mismo_contenido_mismo_nombre(tmp_path):
    a = _ctx(tmp_path / "a")
    b = _ctx(tmp_path / "b")
    assert template_name(a) == template_name(b)


def test_cambiar_un_archivo_cambia_el_nombre(tmp_path):
    ctx = _ctx(tmp_path)
    before = template_name(ctx)
    (ctx / "hooks" / "hook.py").write_bytes(b"print('hook v2')\n")
    assert template_name(ctx) != before


def test_agregar_o_renombrar_un_archivo_cambia_el_nombre(tmp_path):
    ctx = _ctx(tmp_path)
    before = template_name(ctx)
    (ctx / "settings.json").write_bytes(b"{}\n")
    added = template_name(ctx)
    assert added != before
    (ctx / "settings.json").rename(ctx / "otro.json")
    assert template_name(ctx) != added


def test_ignora_caches_de_python(tmp_path):
    ctx = _ctx(tmp_path)
    before = template_name(ctx)
    (ctx / "hooks" / "__pycache__").mkdir()
    (ctx / "hooks" / "__pycache__" / "hook.cpython-312.pyc").write_bytes(b"\x00basura")
    (ctx / "suelto.pyc").write_bytes(b"\x00")
    assert template_name(ctx) == before


def test_crlf_y_lf_dan_el_mismo_nombre(tmp_path):
    lf = _ctx(tmp_path / "lf")
    crlf = _ctx(tmp_path / "crlf")
    (crlf / "Dockerfile").write_bytes((lf / "Dockerfile").read_bytes().replace(b"\n", b"\r\n"))
    assert sandbox_digest(lf) == sandbox_digest(crlf)


def test_e2b_template_fija_el_nombre(tmp_path, monkeypatch):
    monkeypatch.setenv("E2B_TEMPLATE", "plantilla-a-mano")
    assert template_name(_ctx(tmp_path)) == "plantilla-a-mano"


def test_el_sandbox_del_repo_tiene_nombre_estable():
    assert template_name(REPO_SANDBOX) == template_name(REPO_SANDBOX)


class _FakeTemplate:
    """Sustituto de e2b.Template: registra qué se construyó."""

    existing: set[str] = set()
    built: list[str] = []

    def __init__(self, file_context_path: str) -> None:
        self.ctx = file_context_path

    def from_dockerfile(self, path: str) -> _FakeTemplate:
        return self

    @classmethod
    def exists(cls, name: str, **_) -> bool:
        return name in cls.existing

    @classmethod
    def build(cls, tpl, name, **_) -> str:
        cls.built.append(name)
        return "build-info"


@pytest.fixture
def fake_e2b(monkeypatch):
    import e2b

    _FakeTemplate.existing = set()
    _FakeTemplate.built = []
    monkeypatch.setattr(e2b, "Template", _FakeTemplate)
    monkeypatch.setenv("E2B_API_KEY", "e2b_test")
    return _FakeTemplate


def test_build_salta_si_ya_existe(fake_e2b, capsys):
    fake_e2b.existing = {template_name(REPO_SANDBOX)}
    assert e2b_template.main([]) == 0
    assert fake_e2b.built == []
    assert "ya existe" in capsys.readouterr().out


def test_build_construye_si_falta(fake_e2b):
    assert e2b_template.main([]) == 0
    assert fake_e2b.built == [template_name(REPO_SANDBOX)]


def test_build_force_reconstruye(fake_e2b):
    fake_e2b.existing = {template_name(REPO_SANDBOX)}
    assert e2b_template.main(["--force"]) == 0
    assert fake_e2b.built == [template_name(REPO_SANDBOX)]


def test_build_sin_api_key(fake_e2b, monkeypatch):
    monkeypatch.delenv("E2B_API_KEY")
    assert e2b_template.main([]) == 2
    assert fake_e2b.built == []


class _FakeAsyncTemplate:
    existing: set[str] = set()

    @classmethod
    async def exists(cls, name: str, **_) -> bool:
        return name in cls.existing


@pytest.fixture
def provider(monkeypatch):
    import e2b

    _FakeAsyncTemplate.existing = set()
    monkeypatch.setattr(e2b, "AsyncTemplate", _FakeAsyncTemplate)
    return e2b_provider.E2BProvider(api_key="e2b_test")


def test_provider_usa_el_nombre_versionado(provider):
    assert provider.template == template_name(REPO_SANDBOX)


def test_ensure_infra_marca_la_plantilla_que_falta(provider, capsys):
    asyncio.run(provider.ensure_infra())
    assert provider.template_ok is False
    assert "falta la plantilla" in capsys.readouterr().out


def test_ensure_infra_marca_la_plantilla_que_existe(provider):
    _FakeAsyncTemplate.existing = {provider.template}
    asyncio.run(provider.ensure_infra())
    assert provider.template_ok is True


def test_create_falla_claro_si_falta_la_plantilla(provider):
    from aigis.providers import NetworkProfile, ProviderError, SandboxSpec

    asyncio.run(provider.ensure_infra())
    spec = SandboxSpec(run_id="r", lane="none", role="unico", network=NetworkProfile("open"))
    with pytest.raises(ProviderError, match="falta la plantilla"):
        asyncio.run(provider.create(spec))
