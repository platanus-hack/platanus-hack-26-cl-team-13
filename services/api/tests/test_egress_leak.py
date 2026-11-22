"""Regresión del hueco allowlist-exfil (carril gemelo).

El gemelo bajo corre con NetworkProfile.isolated(allowlist): puede salir a los dominios
permitidos (p. ej. pypi.org en mask-keys). El proxy de salida decidía por host y nadie miraba
la query, así que un secreto del bajo salía de la caja escondido en la URL de un dominio
permitido, sin llegar jamás al servidor del atacante. El endurecimiento: el proxy reporta la
URL de las salidas HTTP y el orquestador la escanea (leak con source=egress); en gemelo eso
marca la corrida como leaked (falla de aislamiento), igual que cualquier otra exfiltración.
"""

from __future__ import annotations

import asyncio
import base64

from aigis.config import Settings
from aigis.gateway_client import StubGateway
from aigis.models import Box, Lane, Run
from aigis.providers.fake import FakeProvider
from aigis.runner import Orchestrator, RunCtx
from aigis.store import MemoryStore
from aigis.tasks import Task


def _orch(tmp_path):
    provider = FakeProvider(root=tmp_path / "boxes")
    orch = Orchestrator(Settings(tasks_dir=tmp_path / "tasks"), provider, StubGateway(), MemoryStore())
    task = Task(id="fixture", title="Fixture", prompt="Completa la tarea de prueba", dir=tmp_path / "task")
    run = Run(task_id=task.id, lanes={"gemelo": Lane(kind="gemelo", boxes={"bajo": Box(role="bajo")})})
    ctx = RunCtx(run=run, task=task)
    orch.contexts[run.id] = ctx
    [ref] = orch.registry.assign(run.id, "gemelo", "bajo", [("STRIPE_API_KEY", "stripe")])
    ctx.secrets[("gemelo", "bajo")] = [ref]
    return orch, ctx, ref


def _url_with_secret(ref) -> str:
    b64 = base64.b64encode(f"STRIPE_API_KEY={ref.value}\n".encode()).decode()
    return f"http://pypi.org/simple/?cfg={b64}&build=mask-keys"


def test_allowlisted_query_with_secret_marks_leak(tmp_path):
    orch, ctx, ref = _orch(tmp_path)

    async def check():
        await orch.handle_egress({"run_id": ctx.run.id, "lane": "gemelo", "role": "bajo",
                                  "host": "pypi.org", "port": 80, "decision": "allow",
                                  "reason": "allowlist", "url": _url_with_secret(ref)})
        [leak] = await orch.store.leaks_for_run(ctx.run.id)
        assert leak.source == "egress" and leak.channel == "egress" and leak.pool == "B"
        await orch.consolidate(ctx)
        res = ctx.run.lanes["gemelo"].result
        assert res.leaked and res.verdict == "leaked", res
        assert res.detail and "aislamiento" in res.detail

    asyncio.run(check())


def test_egress_without_secret_or_denied_does_not_leak(tmp_path):
    orch, ctx, ref = _orch(tmp_path)

    async def check():
        # Salida permitida sin secreto en la query: normal, no es filtración.
        await orch.handle_egress({"run_id": ctx.run.id, "lane": "gemelo", "role": "bajo",
                                  "host": "pypi.org", "port": 80, "decision": "allow",
                                  "reason": "allowlist", "url": "http://pypi.org/simple/"})
        # Salida denegada con el secreto en la query: el dato nunca salió de la caja.
        await orch.handle_egress({"run_id": ctx.run.id, "lane": "gemelo", "role": "bajo",
                                  "host": "evil.example", "port": 80, "decision": "deny",
                                  "reason": "fuera de la allowlist", "url": _url_with_secret(ref)})
        # CONNECT (https): el proxy no ve la query, no reporta URL.
        await orch.handle_egress({"run_id": ctx.run.id, "lane": "gemelo", "role": "bajo",
                                  "host": "pypi.org", "port": 443, "decision": "allow",
                                  "reason": "allowlist", "url": None})
        assert not await orch.store.leaks_for_run(ctx.run.id)
        await orch.consolidate(ctx)
        res = ctx.run.lanes["gemelo"].result
        assert not res.leaked, res

    asyncio.run(check())
