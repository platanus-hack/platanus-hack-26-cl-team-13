"""Carriles de defensa.

Cada carril define cómo se prepara su red y qué hace en los hooks del agente.
La garantía del Gemelo no depende de sus hooks: la dan la red y la sustitución
de secretos. Los hooks del carril gemelo solo dan mensajes útiles y registran.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from ..models import Box
    from ..providers import Sandbox
    from ..runner import Orchestrator, RunCtx

Decision = tuple[Literal["allow", "deny"], str | None]
ALLOW: Decision = ("allow", None)

NET_FAIL = re.compile(
    r"(Could not resolve host|Connection refused|Failed to connect|Network is unreachable|"
    r"Temporary failure in name resolution|Name or service not known|blocked by network policy|"
    r"403 Forbidden.*aigis|Connection timed out|getaddrinfo failed|No route to host)",
    re.I,
)


@dataclass
class HookCtx:
    orch: Orchestrator
    rc: RunCtx
    lane: str
    role: str
    box: Box
    sb: Sandbox
    step: int

    async def emit(self, type: str, data: dict[str, Any]) -> None:
        if type == "net.blocked":
            self.rc.bump(self.lane, "net.blocked")
        await self.orch.bus.emit(self.rc.run.id, type, data, lane=self.lane, role=self.role, step=self.step,
                                 mode=self.rc.run.mode)


class Defense:
    """Por defecto deja pasar todo y registra intentos de red fallidos."""

    hook_fail: Literal["open", "closed"] = "open"

    async def on_pre(self, ctx: HookCtx, tool: str, tool_input: dict) -> Decision:
        return ALLOW

    async def on_post(self, ctx: HookCtx, tool: str, tool_input: dict, tool_response: Any) -> None:
        await report_net_failure(ctx, tool, tool_input, tool_response)


def response_text(tool_response: Any) -> str:
    if tool_response is None:
        return ""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        parts = [str(tool_response.get(k, "")) for k in ("stdout", "stderr", "output", "result", "content", "error")]
        joined = "\n".join(p for p in parts if p)
        if joined:
            return joined
    import json

    return json.dumps(tool_response, ensure_ascii=False, default=str)


async def report_net_failure(ctx: HookCtx, tool: str, tool_input: dict, tool_response: Any) -> None:
    text = response_text(tool_response)
    m = NET_FAIL.search(text)
    if m:
        target = tool_input.get("command") or tool_input.get("url") or ""
        await ctx.emit("net.blocked", {"tool": tool, "target": str(target)[:500], "signal": m.group(0)})


def get_defense(kind: str, role: str, *, scripted: bool = False, allow_domains: list[str] | None = None) -> Defense:
    from .claude_native import EmulatedAutoMode, EmulatedSandbox, NativeObserver
    from .fides import FidesDefense
    from .gemelo import TwinLow, TwinHigh
    from .monitor import MonitorDefense
    from .none import NoDefense

    if kind == "none":
        return NoDefense()
    if kind == "cc_sandbox":
        return EmulatedSandbox(allow_domains or []) if scripted else NativeObserver()
    if kind == "auto_mode":
        return EmulatedAutoMode() if scripted else NativeObserver()
    if kind == "monitor":
        return MonitorDefense()
    if kind == "fides":
        return FidesDefense()
    if kind == "gemelo":
        return TwinHigh() if role == "alto" else TwinLow()
    raise ValueError(f"carril desconocido: {kind}")
