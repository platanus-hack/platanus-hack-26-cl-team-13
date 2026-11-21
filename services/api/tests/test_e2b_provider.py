"""Suite de conformidad del provider E2B. Marcada `e2b`: necesita E2B_API_KEY y la plantilla.

    E2B_API_KEY=... uv run pytest -m e2b -q

Mismos escenarios que la suite Docker, con un host público (example.com) en el papel del
gateway, porque en E2B el gateway es una URL pública. Las comprobaciones miran la
respuesta HTTP: en E2B una conexión bloqueada puede parecer abierta.
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.e2b

if not os.environ.get("E2B_API_KEY"):
    pytest.skip("falta E2B_API_KEY", allow_module_level=True)

from gemelo.config import get_settings  # noqa: E402
from gemelo.providers import NetworkProfile, SandboxSpec, run  # noqa: E402

GATEWAY = "https://example.com"
OTHER = "https://www.wikipedia.org"


@pytest.fixture(scope="module")
def provider():
    os.environ["GEMELO_GATEWAY_URL_SANDBOX"] = GATEWAY
    os.environ["GEMELO_PUBLIC_BASE_URL"] = GATEWAY
    get_settings.cache_clear()
    from gemelo.providers.e2b import E2BProvider

    return E2BProvider()


def _spec(net: NetworkProfile, role="unico") -> SandboxSpec:
    return SandboxSpec(run_id="run_conformidad_e2b", lane="none", role=role, network=net, ttl_s=600)


async def _code(p, sb, url, *extra):
    r = await run(p, sb, ["curl", "-s", "-m", "10", "-o", "/dev/null", "-w", "%{http_code}", *extra, url], timeout=30)
    return r.stdout.strip()


def test_tools_and_no_credentials(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.gateway_only()))
        try:
            for cmd in (["claude", "--version"], ["git", "--version"], ["python", "--version"]):
                assert (await run(provider, sb, cmd, timeout=60)).exit_code == 0, cmd
            env = (await run(provider, sb, ["env"])).stdout
            assert "E2B_API_KEY" not in env and "ANTHROPIC_API_KEY" not in env
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_isolated_only_gateway_and_allowlist(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.isolated(["pypi.org"])))
        try:
            assert await _code(provider, sb, GATEWAY) == "200"
            assert (await _code(provider, sb, "https://pypi.org/simple/")) in ("200", "301", "302")
            assert await _code(provider, sb, OTHER) != "200"
            assert await _code(provider, sb, "https://1.1.1.1") != "200"
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_isolated_cannot_resolve_or_use_public_dns(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.gateway_only()))
        try:
            r = await run(provider, sb, ["sh", "-c", "timeout 8 getent hosts gemelo-dns-leak-probe.example.org; echo rc=$?"])
            assert "rc=0" not in r.stdout
            # 8.8.8.8 queda abierto en E2B cuando hay dominios: sin resolv.conf nadie lo usa,
            # pero una consulta directa sí sale. Se documenta como límite si esto pasa.
            r = await run(provider, sb, ["sh", "-c", "python3 -c \"import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);"
                                                     "s.settimeout(4);s.sendto(bytes.fromhex('abcd01000001000000000000076578616d706c6503636f6d0000010001'),('8.8.8.8',53));"
                                                     "print('dns-directo-responde', len(s.recvfrom(512)[0]))\" 2>&1 | tail -1"])
            print("consulta directa a 8.8.8.8:", r.stdout)
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_open_and_hot_cut_keeps_files(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.open()))
        try:
            await provider.write_files(sb, {"/workspace/f.txt": "hola"})
            assert await _code(provider, sb, OTHER) == "200"
            await provider.set_network(sb, NetworkProfile.gateway_only())
            assert await _code(provider, sb, OTHER) != "200"
            assert await _code(provider, sb, GATEWAY) == "200"
            assert (await provider.read_file(sb, "/workspace/f.txt")) == b"hola"
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_destroy_run_cleans(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.gateway_only()))
        assert any(b.id == sb.id for b in await provider.list("run_conformidad_e2b"))
        await provider.destroy_run("run_conformidad_e2b")
        # El listado de E2B tarda unos segundos en reflejar el kill
        for _ in range(15):
            if not any(b.id == sb.id for b in await provider.list("run_conformidad_e2b")):
                break
            await asyncio.sleep(1)
        else:
            raise AssertionError("la caja sigue listada 15 s después de destroy_run")
    asyncio.run(go())
