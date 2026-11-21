"""Provider falso: cada caja es una carpeta temporal y sus comandos son procesos del host.

Solo para tests del orquestador sin Docker. No aísla nada. La política de red se
escribe en `<raíz>/.net.json` y la respeta el agente con guion (`scripted_agent.py`),
que la relee antes de cada petición, así el corte en caliente de FIDES se puede probar.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from ..config import get_settings
from . import ExecEvent, NetworkProfile, Sandbox, SandboxProvider, SandboxSpec

_ENV_KEEP = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "COMSPEC", "PATHEXT", "WINDIR", "HOME",
             "USERPROFILE", "LANG")


class FakeProvider(SandboxProvider):
    name = "fake"

    def __init__(self, root: Path | None = None, gateway_hosts: tuple[str, ...] = ()) -> None:
        self.root = Path(root or tempfile.mkdtemp(prefix="gemelo-fake-"))
        self.boxes: dict[str, Sandbox] = {}
        self.opt_dir = get_settings().sandbox_dir
        self.gateway_hosts = gateway_hosts
        self._n = 0

    def _box_root(self, sb: Sandbox) -> Path:
        return self.root / sb.id

    def map_path(self, sb: Sandbox, path: str) -> Path:
        if path.startswith("/opt/gemelo"):
            return self.opt_dir / path[len("/opt/gemelo"):].lstrip("/")
        if path.startswith("/"):
            return self._box_root(sb) / path.lstrip("/")
        return self._box_root(sb) / "workspace" / path

    def _write_net(self, sb: Sandbox) -> None:
        prof = sb.network or NetworkProfile.open()
        (self._box_root(sb) / ".net.json").write_text(
            json.dumps({"kind": prof.kind, "allowlist": list(prof.allowlist), "always": list(self.gateway_hosts)}),
            "utf-8",
        )

    async def create(self, spec: SandboxSpec) -> Sandbox:
        self._n += 1
        sb = Sandbox(id=f"fake-{spec.run_id[-8:]}-{spec.lane}-{spec.role}-{self._n}", spec=spec,
                     ip=f"10.99.0.{self._n}", network=spec.network)
        r = self._box_root(sb)
        for d in ("workspace", "home/agent", "handoff", "tmp"):
            (r / d).mkdir(parents=True, exist_ok=True)
        self._write_net(sb)
        self.boxes[sb.id] = sb
        return sb

    def _map_cmd(self, sb: Sandbox, cmd: list[str]) -> list[str]:
        out = []
        for i, a in enumerate(cmd):
            if i == 0 and a in ("python3", "python"):
                out.append(sys.executable)
            elif a.startswith(("/workspace", "/opt/gemelo", "/handoff", "/tmp/")):
                out.append(str(self.map_path(sb, a)))
            else:
                out.append(a)
        return out

    async def exec(
        self, sb: Sandbox, cmd: list[str], *, env: dict[str, str] | None = None,
        user: str = "agent", cwd: str = "/workspace", timeout: float | None = None,
    ) -> AsyncIterator[ExecEvent]:
        full_env = {k: v for k, v in os.environ.items() if k in _ENV_KEEP}
        full_env.update(sb.spec.env)
        full_env.update(env or {})
        full_env["GEMELO_FAKE_ROOT"] = str(self._box_root(sb))
        full_env["GEMELO_FAKE_NET_FILE"] = str(self._box_root(sb) / ".net.json")
        full_env["PYTHONIOENCODING"] = "utf-8"
        proc = await asyncio.create_subprocess_exec(
            *self._map_cmd(sb, cmd), cwd=str(self.map_path(sb, cwd)), env=full_env,
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
        done = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout if timeout else None
        try:
            while done < 2:
                remaining = None if deadline is None else max(0.01, deadline - loop.time())
                ev = await asyncio.wait_for(q.get(), remaining)
                if ev is None:
                    done += 1
                    continue
                yield ev
            code = await proc.wait()
            yield ExecEvent("exit", str(code))
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            for t in tasks:
                t.cancel()

    async def write_files(self, sb: Sandbox, files: dict[str, bytes | str], mode: int = 0o644,
                          owner: str = "agent") -> None:
        for path, data in files.items():
            p = self.map_path(sb, path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data.encode() if isinstance(data, str) else data)

    async def read_file(self, sb: Sandbox, path: str) -> bytes:
        return self.map_path(sb, path).read_bytes()

    async def list_dir(self, sb: Sandbox, path: str) -> list[str]:
        p = self.map_path(sb, path)
        return sorted(x.name for x in p.iterdir() if x.is_file()) if p.exists() else []

    async def set_network(self, sb: Sandbox, profile: NetworkProfile) -> None:
        sb.network = profile
        self._write_net(sb)

    async def destroy(self, sb: Sandbox) -> None:
        self.boxes.pop(sb.id, None)
        shutil.rmtree(self._box_root(sb), ignore_errors=True)

    async def list(self, run_id: str | None = None) -> list[Sandbox]:
        return [b for b in self.boxes.values() if run_id is None or b.spec.run_id == run_id]
