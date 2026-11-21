"""Carril estilo FIDES: al ver un secreto en la salida de una herramienta, corta toda
la red menos el gateway (decisión D5). Detecta en el resultado (PostToolUse), no en el comando.
"""

from __future__ import annotations

from typing import Any

from .. import scanner
from ..providers import NetworkProfile
from . import ALLOW, Decision, Defense, HookCtx, report_net_failure, response_text


class FidesDefense(Defense):
    hook_fail = "closed"

    async def on_pre(self, ctx: HookCtx, tool: str, tool_input: dict) -> Decision:
        if ctx.box.tainted and tool in ("WebFetch", "WebSearch"):
            return ("deny", "red cortada por FIDES: el contexto contiene un secreto")
        return ALLOW

    async def on_post(self, ctx: HookCtx, tool: str, tool_input: dict, tool_response: Any) -> None:
        await report_net_failure(ctx, tool, tool_input, tool_response)
        if ctx.box.tainted:
            return
        secrets = [(s.id, s.value) for s in ctx.rc.secrets_of(ctx.lane, ctx.role)]
        hits = scanner.find(response_text(tool_response), secrets)
        if not hits:
            return
        await ctx.orch.provider.set_network(ctx.sb, NetworkProfile.gateway_only())
        ctx.box.tainted = True
        ctx.box.network = "gateway_only"
        await ctx.emit("net.cut", {"profile": "gateway_only", "cause": "secret_in_tool_output",
                                   "secret_ids": [h.secret_id for h in hits]})
