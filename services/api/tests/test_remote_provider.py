"""RemoteProvider contra sandbox-host, con el provider fake detrás (sin Docker ni red)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from aigis import sandbox_host
from aigis.providers import NetworkProfile, ProviderError, SandboxSpec, get_provider, run
from aigis.providers.fake import FakeProvider
from aigis.providers.remote import RemoteProvider, sb_from_dict, sb_to_dict

TOKEN = "t-prueba"


def _remote(tmp_path, monkeypatch, token: str = TOKEN) -> tuple[RemoteProvider, FakeProvider]:
    monkeypatch.setattr(sandbox_host, "TOKEN", TOKEN)
    fake = FakeProvider(root=tmp_path / "boxes")
    app = sandbox_host.create_app(provider=fake)
    rp = RemoteProvider(url="http://sbx", token=token)
    rp.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sbx",
                                headers={"Authorization": f"Bearer {token}"})
    return rp, fake


def test_fabrica_devuelve_proveedor_remoto():
    assert get_provider("remote", url="http://x", token="y").name == "remote"


def test_serializacion_ida_y_vuelta():
    spec = SandboxSpec(run_id="r1", lane="gemelo", role="high", network=NetworkProfile.isolated(["pypi.org"]),
                       env={"A": "1"}, labels={"x": "y"})
    from aigis.providers import Sandbox

    sb = Sandbox(id="abc", spec=spec, ip="10.0.0.2", network=NetworkProfile.gateway_only())
    back = sb_from_dict(sb_to_dict(sb))
    assert back.spec == spec and back.network == sb.network and back.ip == "10.0.0.2"


def test_ciclo_completo_por_http(tmp_path, monkeypatch):
    rp, fake = _remote(tmp_path, monkeypatch)

    async def flujo():
        sb = await rp.create(SandboxSpec(run_id="run_x", lane="none", role="main", network=NetworkProfile.open()))
        assert sb.id in fake.boxes
        await rp.write_files(sb, {"/workspace/a.txt": "hola", "/workspace/sub/b.bin": b"\x00\x01"})
        assert await rp.read_file(sb, "/workspace/a.txt") == b"hola"
        assert await rp.list_dir(sb, "/workspace") == ["a.txt"]
        res = await run(rp, sb, ["python3", "-c", "print('uno'); print('dos')"])
        assert res.exit_code == 0 and res.stdout.splitlines() == ["uno", "dos"]
        await rp.set_network(sb, NetworkProfile.gateway_only())
        assert fake.boxes[sb.id].network == NetworkProfile.gateway_only()
        assert [x.id for x in await rp.list("run_x")] == [sb.id]
        await rp.destroy(sb)
        await rp.destroy(sb)  # idempotente
        assert await rp.list("run_x") == []

    asyncio.run(flujo())


def test_sin_token_correcto_rechaza(tmp_path, monkeypatch):
    rp, _ = _remote(tmp_path, monkeypatch, token="otro")
    with pytest.raises(ProviderError, match="401"):
        asyncio.run(rp.list())


def test_rutas_relativas_rechazadas(tmp_path, monkeypatch):
    rp, _ = _remote(tmp_path, monkeypatch)

    async def flujo():
        sb = await rp.create(SandboxSpec(run_id="run_y", lane="none", role="main", network=NetworkProfile.open()))
        with pytest.raises(ProviderError, match="422"):
            await rp.write_files(sb, {"/workspace/../etc/x": "no"})

    asyncio.run(flujo())
