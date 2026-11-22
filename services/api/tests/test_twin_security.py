"""Regresiones del traspaso y de la entrega del carril gemelo."""

import asyncio

import pytest

from aigis import accept, handoff
from aigis.config import Settings
from aigis.gateway_client import StubGateway
from aigis.models import Box, Lane, Run
from aigis.providers import ExecResult, NetworkProfile, SandboxSpec
from aigis.providers.fake import FakeProvider
from aigis.runner import Orchestrator, RunCtx
from aigis.store import MemoryStore
from aigis.tasks import Task


@pytest.fixture
def twin(tmp_path):
    provider = FakeProvider(root=tmp_path / "boxes")
    orch = Orchestrator(Settings(tasks_dir=tmp_path / "tasks"), provider, StubGateway(), MemoryStore())
    task = Task(id="fixture", title="Fixture", prompt="Completa la tarea de prueba", dir=tmp_path / "task")
    run = Run(task_id=task.id, lanes={"gemelo": Lane(kind="gemelo", boxes={
        "alto": Box(role="alto"), "bajo": Box(role="bajo"),
    })})
    return orch, RunCtx(run=run, task=task)


def test_handoff_only_delivers_high_side_files(twin):
    orch, ctx = twin
    provider = orch.provider

    async def check():
        high = await provider.create(SandboxSpec(ctx.run.id, "gemelo", "alto", NetworkProfile.open()))
        low = await provider.create(SandboxSpec(ctx.run.id, "gemelo", "bajo", NetworkProfile.gateway_only()))
        ctx.sandboxes.update({("gemelo", "alto"): high, ("gemelo", "bajo"): low})
        await provider.write_files(high, {f"{handoff.HIGH_DIR}/reference.txt": "public reference fixture"})
        await provider.write_files(low, {f"{handoff.HIGH_DIR}/local.txt": "private workspace fixture"})

        [name] = await handoff.sync_dir(orch, ctx)
        delivered = await provider.read_file(low, f"{handoff.LOW_DIR}/{name}")
        assert handoff.OPEN.encode() in delivered
        assert b"public reference fixture" in delivered
        assert b"private workspace fixture" not in delivered
        assert await provider.list_dir(low, handoff.LOW_DIR) == [name]
        assert await provider.list_dir(high, handoff.HIGH_DIR) == ["reference.txt"]
        assert await provider.list_dir(high, handoff.LOW_DIR) == []
        assert await handoff.sync_dir(orch, ctx) == []

    asyncio.run(check())


@pytest.mark.parametrize("contains_marker", [False, True], ids=["clean", "marked"])
def test_twin_acceptance_limits_test_network_and_checks_diff(twin, monkeypatch, contains_marker):
    orch, ctx = twin
    [marker] = orch.registry.assign(ctx.run.id, "gemelo", "bajo", [("FIXTURE_TOKEN", "generic")])
    ctx.secrets[("gemelo", "bajo")] = [marker]
    value = marker.value if contains_marker else "public fixture"

    async def fixture_diff(*args):
        return f"@@ -1 +1 @@\n-old\n+{value}\n"

    async def run_tests(provider, sandbox, command, **kwargs):
        assert command == ctx.task.test_cmd
        assert sandbox.network == NetworkProfile.gateway_only()
        return ExecResult(exit_code=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(accept, "take_diff", fixture_diff)
    monkeypatch.setattr(accept, "run", run_tests)

    async def check():
        profile = NetworkProfile.isolated(["packages.example.invalid"])
        spec = SandboxSpec(ctx.run.id, "gemelo", "bajo", profile)
        ctx.sandboxes[("gemelo", "bajo")] = await orch.provider.create(spec)
        ctx.box("gemelo", "bajo").network = "isolated"
        ctx.acceptance[("gemelo", "bajo")] = await accept.evaluate(orch, ctx, "gemelo", "bajo")
        await orch.consolidate(ctx)

        result = ctx.run.lanes["gemelo"].result
        assert result.task_passed is True
        assert result.delivered is (not contains_marker)
        assert result.verdict == ("rejected_leak" if contains_marker else "delivered")
        stored = await orch.store.get_diff(ctx.run.id, "gemelo", "bajo")
        assert stored and marker.value not in stored
        assert ("public fixture" in stored) is (not contains_marker)

    asyncio.run(check())
