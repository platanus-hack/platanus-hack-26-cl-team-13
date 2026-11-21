"""Proveedor remoto: las cajas corren en otra máquina con `aigis.sandbox_host`.

El orquestador habla por HTTP con sandbox-host (en la demo, la VM gemelo-sbx por la VPN),
que envuelve un LocalProvider con gVisor. La interfaz es la misma; aquí solo hay
serialización y transporte. `exec` llega en NDJSON, una línea por evento.

Configuración (prefijo AIGIS_): SANDBOX_HOST_URL, SANDBOX_HOST_TOKEN y EGRESS_TOKEN
(el mismo que usa el proxy de la VM para reportar a /internal/egress).
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import asdict

import httpx

from ..config import get_settings
from . import ExecEvent, NetworkProfile, ProviderError, QuotaExceededError, Sandbox, SandboxProvider, SandboxSpec

# --- Serialización (compartida con sandbox_host) ---------------------------


def net_to_dict(n: NetworkProfile | None) -> dict | None:
    return None if n is None else {"kind": n.kind, "allowlist": sorted(n.allowlist)}


def net_from_dict(d: dict | None) -> NetworkProfile | None:
    return None if d is None else NetworkProfile(d["kind"], frozenset(d.get("allowlist") or ()))


def spec_to_dict(s: SandboxSpec) -> dict:
    d = asdict(s)
    d["network"] = net_to_dict(s.network)
    return d


def spec_from_dict(d: dict) -> SandboxSpec:
    return SandboxSpec(**{**d, "network": net_from_dict(d["network"])})


def sb_to_dict(sb: Sandbox) -> dict:
    return {"id": sb.id, "spec": spec_to_dict(sb.spec), "ip": sb.ip, "network": net_to_dict(sb.network)}


def sb_from_dict(d: dict) -> Sandbox:
    return Sandbox(id=d["id"], spec=spec_from_dict(d["spec"]), ip=d.get("ip"), network=net_from_dict(d.get("network")))


# --- Cliente ---------------------------------------------------------------


class RemoteProvider(SandboxProvider):
    name = "remote"

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        s = get_settings()
        self.url = (url or s.sandbox_host_url).rstrip("/")
        if not self.url:
            raise ProviderError("AIGIS_SANDBOX_HOST_URL vacía: falta la dirección de sandbox-host")
        # /internal/egress del orquestador valida contra este token
        self.admin_token = s.egress_token or None
        self.http = httpx.AsyncClient(
            base_url=self.url, timeout=httpx.Timeout(120, connect=5),
            headers={"Authorization": f"Bearer {token or s.sandbox_host_token}"},
        )

    async def _req(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = await self.http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise ProviderError(f"sandbox-host no responde ({self.url}): {type(e).__name__}") from e
        if r.status_code == 429:
            raise QuotaExceededError(r.text[:300])
        if r.status_code >= 400:
            raise ProviderError(f"sandbox-host {method} {path}: {r.status_code} {r.text[:300]}")
        return r

    async def ensure_infra(self) -> None:
        """La infraestructura la levanta sandbox-host al arrancar. Aquí solo se comprueba."""
        try:
            await self._req("GET", "/health")
        except ProviderError as e:
            print(f"aviso: {e}", flush=True)

    async def health(self) -> dict:
        return (await self._req("GET", "/health")).json()

    async def create(self, spec: SandboxSpec) -> Sandbox:
        return sb_from_dict((await self._req("POST", "/sandboxes", json=spec_to_dict(spec))).json())

    async def set_network(self, sb: Sandbox, network: NetworkProfile) -> None:
        await self._req("PUT", f"/sandboxes/{sb.id}/network", json=net_to_dict(network))
        sb.network = network

    async def write_files(self, sb: Sandbox, files: dict[str, bytes | str], mode: int = 0o644,
                          owner: str = "agent") -> None:
        enc = {p: base64.b64encode(d.encode() if isinstance(d, str) else d).decode() for p, d in files.items()}
        await self._req("POST", f"/sandboxes/{sb.id}/files", json={"files": enc, "mode": mode, "owner": owner})

    async def read_file(self, sb: Sandbox, path: str) -> bytes:
        return (await self._req("GET", f"/sandboxes/{sb.id}/file", params={"path": path})).content

    async def list_dir(self, sb: Sandbox, path: str) -> list[str]:
        return (await self._req("GET", f"/sandboxes/{sb.id}/dir", params={"path": path})).json()

    async def destroy(self, sb: Sandbox) -> None:
        try:
            await self._req("DELETE", f"/sandboxes/{sb.id}")
        except ProviderError as e:
            if "404" not in str(e):
                raise

    async def list(self, run_id: str | None = None) -> list[Sandbox]:
        params = {"run_id": run_id} if run_id else None
        return [sb_from_dict(d) for d in (await self._req("GET", "/sandboxes", params=params)).json()]

    async def exec(
        self, sb: Sandbox, cmd: list[str], *, env: dict[str, str] | None = None,
        user: str = "agent", cwd: str = "/workspace", timeout: float | None = None,
    ) -> AsyncIterator[ExecEvent]:
        body = {"cmd": cmd, "env": env or {}, "user": user, "cwd": cwd, "timeout": timeout}
        try:
            async with self.http.stream("POST", f"/sandboxes/{sb.id}/exec", json=body,
                                        timeout=httpx.Timeout(None, connect=5)) as r:
                if r.status_code >= 400:
                    raise ProviderError(f"sandbox-host exec: {r.status_code} {(await r.aread())[:300]!r}")
                got_exit = False
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    ev = json.loads(line)
                    if ev["stream"] == "error":
                        if ev["data"] == "timeout":
                            raise TimeoutError("exec superó su timeout en sandbox-host")
                        raise ProviderError(f"sandbox-host exec: {ev['data']}")
                    got_exit = got_exit or ev["stream"] == "exit"
                    yield ExecEvent(ev["stream"], ev["data"])
                if not got_exit:
                    raise ProviderError("sandbox-host cortó el exec sin código de salida")
        except httpx.HTTPError as e:
            raise ProviderError(f"sandbox-host exec: {type(e).__name__}: {e}") from e
