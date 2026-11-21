"""Proveedor local (Docker), vía el CLI `docker`.

Topología (design de add-sandbox-provider):
  aigis-net-<caja>  una red internal: true por caja, solo con esa caja y el proxy.
                     Sin salida y sin vista de las otras cajas.
  aigis_egress      bridge normal con enable_icc=false. Cajas con perfil abierto y el
                     proxy. Salen a internet pero no se ven entre ellas.
  aigis-proxy       contenedor en todas esas redes. Único puente. Política por IP de origen.

Ninguna caja alcanza a otra: así el gemelo bajo no puede pasarle un secreto al alto
(que sí tiene internet) por la red interna.

Toda caja recibe HTTP(S)_PROXY hacia el proxy, así el gateway y los hooks del
orquestador (en el host) se alcanzan por `host.docker.internal` a través de él.
Una caja aislada que borra sus variables de proxy queda sin ruta: el bloqueo lo
aplica la red, no código dentro de la caja.
"""

from __future__ import annotations

import asyncio
import io
import os
import json
import secrets
import tarfile
import time
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath

import httpx

from ..config import get_settings
from . import ExecEvent, NetworkProfile, Sandbox, SandboxProvider, SandboxSpec

NET_EGRESS = "aigis_egress"
PROXY_NAME = "aigis-proxy"
# Alias solo en las redes internas de cada caja: una caja abierta (en dos redes) igual
# llega al proxy por su IP interna, que es la que tiene política.
PROXY_ALIAS = "aigis-egress-proxy"
PROXY_IMAGE = "aigis-proxy:dev"
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "aigis-sandbox:local")  # mismo tag que `make sandbox-image`
ADMIN_URL = "http://127.0.0.1:3129"
UIDS = {"agent": 1001, "root": 0}


class DockerError(RuntimeError):
    pass


async def docker(*args: str, input: bytes | None = None, check: bool = True, timeout: float = 120) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        "docker", *args, stdin=asyncio.subprocess.PIPE if input is not None else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(input), timeout)
    except (TimeoutError, asyncio.TimeoutError):
        proc.kill()
        raise
    if check and proc.returncode != 0:
        raise DockerError(f"docker {' '.join(args[:3])}: {err.decode(errors='replace').strip()[:500]}")
    return proc.returncode, out, err


class LocalProvider(SandboxProvider):
    name = "local"

    def __init__(self, image: str = SANDBOX_IMAGE, runtime: str | None = None) -> None:
        s = get_settings()
        self.image = image
        self.runtime = runtime or s.sandbox_runtime or None
        self.admin_token = s.egress_token or secrets.token_urlsafe(24)
        self.host_ip = s.sandbox_host_ip or "host-gateway"
        self.resolv = s.sandbox_resolv or None
        host = "host.docker.internal"
        gw = httpx.URL(s.gateway_url_sandbox)
        self.always = sorted({f"{host}:{s.port}", f"{gw.host}:{gw.port or 80}"})
        self.events_url = f"http://{host}:{s.port}/internal/egress"
        atk = httpx.URL(s.attacker_url_sandbox)
        self.open_also = [f"{atk.host}:{atk.port or 80}"]
        self.boxes: dict[str, Sandbox] = {}
        self.nets: dict[str, str] = {}
        self._subnet_i = secrets.randbelow(4096)
        self.http = httpx.AsyncClient(timeout=5, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.repo_root = s.sandbox_dir.parent

    # ---------- infraestructura ----------

    async def ensure_infra(self, build: bool = True) -> None:
        for image, ctx in ((self.image, "sandbox"), (PROXY_IMAGE, "egress_proxy")):
            code, _, _ = await docker("image", "inspect", image, check=False)
            if code != 0:
                if not build:
                    raise DockerError(f"falta la imagen {image}: make sandbox-image")
                await docker("build", "-t", image, str(self.repo_root / ctx), timeout=1200)
        await docker("rm", "-f", PROXY_NAME, check=False)
        await self._reap_networks()
        code, out, _ = await docker("network", "inspect", "-f",
                                    '{{index .Options "com.docker.network.bridge.enable_icc"}}', NET_EGRESS, check=False)
        if code == 0 and out.decode().strip() != "false":
            await docker("network", "rm", NET_EGRESS)  # versión vieja sin aislamiento entre cajas
            code = 1
        if code != 0:
            await docker("network", "create", "-o", "com.docker.network.bridge.enable_icc=false",
                         "--label", "aigis.infra=1", NET_EGRESS)
        await docker(
            "run", "-d", "--name", PROXY_NAME, "--label", "aigis.infra=1", "--network", NET_EGRESS,
            "--add-host", f"host.docker.internal:{self.host_ip}", "-p", "127.0.0.1:3129:3129",
            "-e", f"ADMIN_TOKEN={self.admin_token}", "-e", f"ALWAYS={','.join(self.always)}",
            "-e", f"EVENTS_URL={self.events_url}", "-e", f"OPEN_ALSO={','.join(self.open_also)}", PROXY_IMAGE,
        )
        for _ in range(50):
            try:
                if (await self.http.get(f"{ADMIN_URL}/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
        raise DockerError("el proxy de salida no respondió")

    async def _create_box_network(self, name: str, run_id: str) -> str:
        """Red interna propia de la caja, con subred /28 en 10.213.0.0/16, y el proxy adentro."""
        net = f"{name}-net"
        await docker("network", "rm", net, check=False)
        last = None
        for _ in range(64):
            self._subnet_i = (self._subnet_i + 1) % 4096
            i = self._subnet_i
            subnet = f"10.213.{i // 16}.{(i % 16) * 16}/28"
            code, _, err = await docker("network", "create", "--internal", "--subnet", subnet,
                                        "--label", f"aigis.run={run_id}", "--label", "aigis.boxnet=1", net,
                                        check=False)
            if code == 0:
                break
            last = err.decode(errors="replace")
        else:
            raise DockerError(f"no hay subred libre para {net}: {last}")
        await docker("network", "connect", "--alias", PROXY_ALIAS, net, PROXY_NAME)
        return net

    async def _remove_box_network(self, net: str) -> None:
        await docker("network", "disconnect", "-f", net, PROXY_NAME, check=False)
        await docker("network", "rm", net, check=False)

    async def _reap_networks(self) -> None:
        code, out, _ = await docker("network", "ls", "--filter", "label=aigis.boxnet=1", "--format", "{{.Name}}",
                                    check=False)
        for net in out.decode().split() if code == 0 else []:
            await self._remove_box_network(net)  # falla si aún tiene cajas: se queda

    async def _policy(self, sb: Sandbox, profile: NetworkProfile) -> None:
        r = await self.http.put(f"{ADMIN_URL}/policies/{sb.ip}", json={
            "run_id": sb.spec.run_id, "lane": sb.spec.lane, "role": sb.spec.role,
            "kind": profile.kind, "allowlist": sorted(profile.allowlist)})
        r.raise_for_status()

    # ---------- ciclo de vida ----------

    async def create(self, spec: SandboxSpec) -> Sandbox:
        name = f"aigis-{spec.run_id[-8:]}-{spec.lane}-{spec.role}"
        env = {**spec.env, "HTTP_PROXY": f"http://{PROXY_ALIAS}:3128", "HTTPS_PROXY": f"http://{PROXY_ALIAS}:3128",
               "http_proxy": f"http://{PROXY_ALIAS}:3128", "https_proxy": f"http://{PROXY_ALIAS}:3128",
               "ALL_PROXY": f"http://{PROXY_ALIAS}:3128", "NO_PROXY": "", "no_proxy": ""}
        net = await self._create_box_network(name, spec.run_id)
        args = [
            "run", "-d", "--name", name, "--hostname", f"{spec.lane}-{spec.role}",
            "--label", f"aigis.run={spec.run_id}", "--label", f"aigis.lane={spec.lane}",
            "--label", f"aigis.role={spec.role}", "--label", f"aigis.expires={int(time.time()) + spec.ttl_s}",
            "--network", net, "--cap-drop", "ALL",
            "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER", "--cap-add", "KILL",
            "--security-opt", "no-new-privileges", "--pids-limit", "512",
            "--cpus", str(spec.cpus), "--memory", f"{spec.memory_mb}m",
        ]
        if spec.nested_sandbox:
            # bubblewrap crea user, mount y net namespaces: el seccomp y AppArmor por defecto de
            # Docker lo impiden. La red de la caja sigue controlada por el proxy.
            args += ["--security-opt", "seccomp=unconfined", "--security-opt", "apparmor=unconfined"]
        if self.runtime:
            args += ["--runtime", self.runtime]
        if self.resolv:
            # Sin el DNS interno de Docker (no funciona con gVisor): DNS públicos (sin ruta en
            # las cajas aisladas, así A2 se cumple igual) y el proxy por IP fija.
            _, pip, _ = await docker("inspect", "-f", f'{{{{(index .NetworkSettings.Networks "{net}").IPAddress}}}}',
                                     PROXY_NAME)
            args += ["-v", f"{self.resolv}:/etc/resolv.conf:ro", "--add-host", f"{PROXY_ALIAS}:{pip.decode().strip()}"]
        for k, v in env.items():
            args += ["-e", f"{k}={v}"]
        args += [spec.template or self.image, "sleep", "infinity"]
        try:
            _, out, _ = await docker(*args)
        except Exception:
            await self._remove_box_network(net)
            raise
        cid = out.decode().strip()
        sb = Sandbox(id=cid[:12], spec=spec, network=spec.network)
        self.nets[sb.id] = net
        try:
            _, ipb, _ = await docker("inspect", "-f", f'{{{{(index .NetworkSettings.Networks "{net}").IPAddress}}}}', cid)
            sb.ip = ipb.decode().strip()
            # Política antes de abrir la red: nunca hay una caja sin política
            await self._policy(sb, spec.network)
            if spec.network.kind == "open":
                await docker("network", "connect", NET_EGRESS, cid)
        except Exception:
            await docker("rm", "-f", cid, check=False)
            await self._remove_box_network(net)
            raise
        self.boxes[sb.id] = sb
        return sb

    async def set_network(self, sb: Sandbox, profile: NetworkProfile) -> None:
        was_open = (sb.network or sb.spec.network).kind == "open"
        await self._policy(sb, profile)
        if was_open and profile.kind != "open":
            await docker("network", "disconnect", "-f", NET_EGRESS, sb.id, check=False)
        elif not was_open and profile.kind == "open":
            await docker("network", "connect", NET_EGRESS, sb.id)
        sb.network = profile

    async def destroy(self, sb: Sandbox) -> None:
        self.boxes.pop(sb.id, None)
        await docker("rm", "-f", "-v", sb.id, check=False)
        net = self.nets.pop(sb.id, None)
        if net:
            await self._remove_box_network(net)
        if sb.ip:
            try:
                await self.http.delete(f"{ADMIN_URL}/policies/{sb.ip}")
            except httpx.HTTPError:
                pass

    async def list(self, run_id: str | None = None) -> list[Sandbox]:
        flt = f"label=aigis.run={run_id}" if run_id else "label=aigis.run"
        code, out, _ = await docker("ps", "-a", "--filter", flt, "--format", "{{json .}}", check=False)
        if code != 0:
            return []
        res = []
        for line in out.decode().splitlines():
            row = json.loads(line)
            labels = dict(x.split("=", 1) for x in row.get("Labels", "").split(",") if "=" in x)
            known = self.boxes.get(row["ID"][:12])
            if known:
                res.append(known)
                continue
            spec = SandboxSpec(run_id=labels.get("aigis.run", ""), lane=labels.get("aigis.lane", ""),
                               role=labels.get("aigis.role", ""), network=NetworkProfile.gateway_only())
            res.append(Sandbox(id=row["ID"][:12], spec=spec))
        return res

    async def reap(self) -> int:
        """Destruye cajas vencidas por TTL (proceso caído o corrida colgada)."""
        n, now = 0, int(time.time())
        code, out, _ = await docker("ps", "-a", "--filter", "label=aigis.expires", "--format",
                                    '{{.ID}} {{.Label "aigis.expires"}}', check=False)
        for line in out.decode().splitlines() if code == 0 else []:
            cid, _, exp = line.partition(" ")
            if exp.isdigit() and int(exp) < now:
                await docker("rm", "-f", "-v", cid, check=False)
                n += 1
        if n:
            await self._reap_networks()
        return n

    # ---------- ejecución y archivos ----------

    async def exec(
        self, sb: Sandbox, cmd: list[str], *, env: dict[str, str] | None = None,
        user: str = "agent", cwd: str = "/workspace", timeout: float | None = None,
    ) -> AsyncIterator[ExecEvent]:
        args = ["exec", "-i", "-u", user, "-w", cwd]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        proc = await asyncio.create_subprocess_exec(
            "docker", *args, sb.id, *cmd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=2**24,
        )
        q: asyncio.Queue[ExecEvent | None] = asyncio.Queue()

        async def pump(stream, name):
            try:
                async for line in stream:
                    await q.put(ExecEvent(name, line.decode("utf-8", "replace").rstrip("\r\n")))
            finally:
                await q.put(None)

        tasks = [asyncio.create_task(pump(proc.stdout, "stdout")), asyncio.create_task(pump(proc.stderr, "stderr"))]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout if timeout else None
        done = 0
        finished = False
        try:
            while done < 2:
                remaining = None if deadline is None else max(0.01, deadline - loop.time())
                ev = await asyncio.wait_for(q.get(), remaining)
                if ev is None:
                    done += 1
                    continue
                yield ev
            yield ExecEvent("exit", str(await proc.wait()))
            finished = True
        finally:
            if not finished:
                # Matar el cliente no mata el proceso dentro de la caja
                if user == "agent":
                    await docker("exec", "-u", "root", sb.id, "pkill", "-KILL", "-u", "agent", check=False, timeout=15)
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            for t in tasks:
                t.cancel()

    async def write_files(self, sb: Sandbox, files: dict[str, bytes | str], mode: int = 0o644,
                          owner: str = "agent") -> None:
        uid = UIDS.get(owner, 1001)
        buf = io.BytesIO()
        dirs: set[str] = set()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for path, data in files.items():
                p = PurePosixPath(path)
                # Directorios intermedios con el mismo dueño, sin tocar los de primer nivel (/tmp, /workspace)
                for parent in reversed(p.parents[:-2] if len(p.parents) > 2 else []):
                    d = str(parent).lstrip("/")
                    if d and d not in dirs:
                        dirs.add(d)
                        ti = tarfile.TarInfo(d)
                        ti.type, ti.mode, ti.uid, ti.gid = tarfile.DIRTYPE, 0o755, uid, uid
                        tar.addfile(ti)
                raw = data.encode() if isinstance(data, str) else data
                ti = tarfile.TarInfo(str(p).lstrip("/"))
                ti.size, ti.mode, ti.uid, ti.gid, ti.mtime = len(raw), mode, uid, uid, int(time.time())
                tar.addfile(ti, io.BytesIO(raw))
        # tar por exec y no `docker cp`: con gVisor la raíz de la caja vive en su propia memoria
        # y `docker cp` escribe en una capa que la caja no ve.
        await docker("exec", "-i", "-u", "root", sb.id, "tar", "-x", "--same-owner", "-C", "/",
                     input=buf.getvalue())

    async def read_file(self, sb: Sandbox, path: str) -> bytes:
        _, out, _ = await docker("exec", "-u", "root", sb.id, "cat", path)
        return out

    async def list_dir(self, sb: Sandbox, path: str) -> list[str]:
        code, out, _ = await docker("exec", "-u", "root", sb.id, "find", path, "-maxdepth", "1", "-type", "f",
                                    "-printf", "%f\\n", check=False)
        return sorted(x for x in out.decode().splitlines() if x) if code == 0 else []


def repo_root() -> Path:
    return get_settings().sandbox_dir.parent


# Nombre anterior, usado en tests y scripts
DockerProvider = LocalProvider
