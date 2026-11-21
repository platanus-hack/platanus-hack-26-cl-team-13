"""Proveedores de sandbox.

Interfaz única que el orquestador usa para crear sandboxes, ejecutar comandos,
leer resultados, cambiar la red y destruirlos, sin saber si detrás hay Docker
(local) o E2B. Se elige con la variable SANDBOX_PROVIDER.

Fusión de la interfaz de add-sandbox-provider (grupo 2) con lo que necesita el
orquestador:
- Se mantienen los perfiles de red (open, isolated, gateway_only = isolated sin
  allowlist), los errores, la fábrica con `local` por defecto y `destroy_run`.
- Las operaciones son asíncronas: el orquestador corre 5 cajas en paralelo con
  asyncio y recibe hooks mientras los agentes ejecutan.
- `create` recibe un `SandboxSpec` (plantilla, red, corrida, carril, rol, env) y el
  repo se copia después con `write_files`, para inyectar el ataque y los secretos
  en el orden correcto (los secretos nunca entran al commit base).
- Se agregan `write_files`, `list_dir` y `list`, y el proveedor `fake` para tests
  sin Docker (no aísla nada).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Literal

VALID_PROVIDERS = ("local", "e2b", "fake", "remote")
DEFAULT_PROVIDER = "local"


# --- Perfiles de red -------------------------------------------------------


@dataclass(frozen=True)
class NetworkProfile:
    """Política de red de un sandbox.

    - open: salida libre a internet.
    - isolated: solo el gateway del modelo y los dominios de la allowlist.
      Con la allowlist vacía es "solo gateway".
    """

    kind: Literal["open", "isolated"]
    allowlist: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.kind == "open" and self.allowlist:
            raise ValueError("El perfil abierto no lleva allowlist")

    @property
    def is_gateway_only(self) -> bool:
        return self.kind == "isolated" and not self.allowlist

    @property
    def label(self) -> str:
        if self.kind == "open":
            return "open"
        if self.is_gateway_only:
            return "gateway_only"
        return f"isolated({','.join(sorted(self.allowlist))})"

    # Atajos usados por el orquestador
    open = staticmethod(lambda: open_network())
    isolated = staticmethod(lambda allowlist=(): isolated(allowlist))
    gateway_only = staticmethod(lambda: gateway_only())


def open_network() -> NetworkProfile:
    return NetworkProfile("open")


def isolated(allowlist: list[str] | tuple[str, ...] | frozenset[str] = ()) -> NetworkProfile:
    return NetworkProfile("isolated", frozenset(allowlist))


def gateway_only() -> NetworkProfile:
    """Destino del corte de red en caliente (decisión D5: todo menos el gateway)."""
    return isolated()


# --- Sandbox y ejecución ---------------------------------------------------


@dataclass
class SandboxSpec:
    run_id: str
    lane: str
    role: str
    network: NetworkProfile
    template: str = ""
    env: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    cpus: float = 1.0
    memory_mb: int = 2048
    ttl_s: int = 1800
    # La caja corre bubblewrap adentro (sandbox nativo de Claude Code): necesita user namespaces
    nested_sandbox: bool = False


@dataclass
class Sandbox:
    """Referencia a un sandbox creado por un proveedor."""

    id: str
    spec: SandboxSpec
    ip: str | None = None
    network: NetworkProfile | None = None

    @property
    def run_id(self) -> str:
        return self.spec.run_id


@dataclass(frozen=True)
class ExecEvent:
    """Evento de un comando en ejecución. El último tiene stream="exit" y el código en data."""

    stream: Literal["stdout", "stderr", "exit"]
    data: str


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


# --- Errores ---------------------------------------------------------------


class ProviderError(Exception):
    """Error de un proveedor de sandboxes."""


class UnknownProviderError(ProviderError):
    """SANDBOX_PROVIDER tiene un valor que no corresponde a ningún proveedor."""


class QuotaExceededError(ProviderError):
    """El proveedor rechazó crear un sandbox por límite de cuota."""


# --- Interfaz --------------------------------------------------------------


class SandboxProvider(ABC):
    """Operaciones que todo proveedor de sandboxes debe implementar."""

    name: str

    @abstractmethod
    async def create(self, spec: SandboxSpec) -> Sandbox:
        """Crea un sandbox desde la plantilla con su red ya aplicada. Nunca existe una caja sin política."""

    @abstractmethod
    def exec(
        self, sb: Sandbox, cmd: list[str], *, env: dict[str, str] | None = None,
        user: str = "agent", cwd: str = "/workspace", timeout: float | None = None,
    ) -> AsyncIterator[ExecEvent]:
        """Ejecuta un comando y entrega su salida en streaming; el último evento es stream="exit"."""

    @abstractmethod
    async def write_files(self, sb: Sandbox, files: dict[str, bytes | str], mode: int = 0o644,
                          owner: str = "agent") -> None:
        """Escribe archivos con rutas absolutas dentro de la caja, creando directorios."""

    @abstractmethod
    async def read_file(self, sb: Sandbox, path: str) -> bytes:
        """Lee un archivo del sandbox."""

    @abstractmethod
    async def list_dir(self, sb: Sandbox, path: str) -> list[str]:
        """Nombres de los archivos (no directorios) de una carpeta."""

    async def git_diff(self, sb: Sandbox, base: str = "HEAD") -> str:
        """git diff del repo de la tarea, sin .env ni archivos de control."""
        await run(self, sb, ["git", "add", "-A"])
        res = await run(self, sb, ["git", "diff", "--cached", "--binary", base, "--", ".",
                                   ":(exclude).env", ":(exclude).aigis", ":(exclude).aigis_tests"])
        return res.stdout

    @abstractmethod
    async def set_network(self, sb: Sandbox, network: NetworkProfile) -> None:
        """Cambia la red de un sandbox en ejecución sin reiniciarlo ni perder su estado."""

    @abstractmethod
    async def destroy(self, sb: Sandbox) -> None:
        """Destruye un sandbox. Idempotente."""

    @abstractmethod
    async def list(self, run_id: str | None = None) -> list[Sandbox]:
        """Sandboxes vivos, de una corrida o de todas."""

    async def destroy_run(self, run_id: str) -> None:
        """Destruye todos los sandboxes de una corrida, aunque el proceso que los creó haya caído."""
        for sb in await self.list(run_id):
            await self.destroy(sb)


async def run(provider: SandboxProvider, sb: Sandbox, cmd: list[str], **kw) -> ExecResult:
    """Ejecuta y junta la salida. Para comandos cortos del orquestador."""
    out, err, code = [], [], -1
    async for ev in provider.exec(sb, cmd, **kw):
        if ev.stream == "stdout":
            out.append(ev.data)
        elif ev.stream == "stderr":
            err.append(ev.data)
        else:
            code = int(ev.data)
    return ExecResult(code, "\n".join(out), "\n".join(err))


# --- Fábrica ---------------------------------------------------------------


def get_provider(name: str | Mapping[str, str] | None = None, **kw) -> SandboxProvider:
    """Devuelve el proveedor pedido, o el de SANDBOX_PROVIDER (por defecto, local).

    Acepta el nombre o un mapping de entorno, como la versión original de la fábrica.
    """
    if name is None or isinstance(name, Mapping):
        env = os.environ if name is None else name
        name = env.get("SANDBOX_PROVIDER", "")
    value = name.strip().lower() or DEFAULT_PROVIDER

    if value == "local":
        from aigis.providers.local import LocalProvider

        return LocalProvider(**kw)
    if value == "e2b":
        from aigis.providers.e2b import E2BProvider

        return E2BProvider(**kw)
    if value == "remote":
        from aigis.providers.remote import RemoteProvider

        return RemoteProvider(**kw)
    if value == "fake":
        from aigis.providers.fake import FakeProvider

        return FakeProvider(**kw)

    raise UnknownProviderError(
        f"SANDBOX_PROVIDER={value!r} no es válido. Valores válidos: {', '.join(VALID_PROVIDERS)}"
    )


__all__ = [
    "DEFAULT_PROVIDER",
    "VALID_PROVIDERS",
    "ExecEvent",
    "ExecResult",
    "NetworkProfile",
    "ProviderError",
    "QuotaExceededError",
    "Sandbox",
    "SandboxProvider",
    "SandboxSpec",
    "UnknownProviderError",
    "gateway_only",
    "get_provider",
    "isolated",
    "open_network",
    "run",
]
