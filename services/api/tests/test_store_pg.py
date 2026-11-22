"""PostgresStore contra un Postgres real en Docker. Marcada `docker`.

    uv run pytest -m docker tests/test_store_pg.py
"""

from __future__ import annotations

import asyncio
import subprocess
import time

import pytest

from .test_docker_provider import _docker_up  # noqa: F401  (salta si no hay Docker)

pytestmark = pytest.mark.docker

PORT = 55432
DSN = f"postgresql://gemelo:gemelo@127.0.0.1:{PORT}/gemelo"


@pytest.fixture(scope="module")
def pg():
    subprocess.run(["docker", "rm", "-f", "aigis-pg-test"], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", "aigis-pg-test", "-p", f"127.0.0.1:{PORT}:5432",
                    "-e", "POSTGRES_USER=gemelo", "-e", "POSTGRES_PASSWORD=gemelo", "-e", "POSTGRES_DB=gemelo",
                    "postgres:16-alpine"], check=True, capture_output=True)
    import psycopg

    for _ in range(60):
        try:
            psycopg.connect(DSN, connect_timeout=2).close()
            break
        except Exception:
            time.sleep(1)
    yield DSN
    subprocess.run(["docker", "rm", "-f", "aigis-pg-test"], capture_output=True)


def test_roundtrip(pg):
    from aigis.models import Event, Leak, Run, SecretRef
    from aigis.store_pg import PostgresStore

    async def go():
        st = PostgresStore(pg)
        await st.open()
        try:
            run = Run(task_id="mask-keys")
            await st.save_run(run)
            run.status = "done"
            await st.save_run(run)
            got = await st.get_run(run.id)
            assert got and got.status == "done" and got.task_id == "mask-keys"
            assert (await st.list_runs())[0].id == run.id
            for i in (1, 2, 3):
                await st.append_event(Event(seq=i, run_id=run.id, type="x", data={"i": i}))
            assert [e.seq for e in await st.events(run.id, after_seq=1)] == [2, 3]
            ref = SecretRef(id="sec_1", pool="B", env_name="K", kind="generic", value="v", run_id=run.id)
            await st.save_secret(ref)
            assert (await st.secrets_for_run(run.id))[0].id == "sec_1"
            await st.save_leak(Leak(run_id=run.id, lane="none", role="unico", secret_id="sec_1", pool="B",
                                    source="attacker", encoding="plain"))
            assert len(await st.leaks_for_run(run.id)) == 1
            await st.save_diff(run.id, "gemelo", "bajo", "diff --git a b")
            assert await st.get_diff(run.id, "gemelo", "bajo") == "diff --git a b"
            await st.save_usage(run.id, {"cost_usd": 0.1})
            assert (await st.get_usage(run.id))["cost_usd"] == 0.1
            assert await st.get_usage("nada") is None
            spent, n = await st.total_cost()
            assert n >= 1 and spent >= 0.1
        finally:
            await st.close()

    asyncio.run(go())


def test_full_run_persists_and_survives_restart(pg, harness):
    """Una corrida completa con provider falso queda en Postgres y se lee con otro Store."""
    from aigis.store_pg import PostgresStore

    async def setup():
        st = PostgresStore(pg)
        await st.open()
        return st

    with harness.client() as c:
        run_id = c.post("/runs", json={"task_id": "mask-keys"}).json()["run_id"]
    harness.wait_run(run_id)
    run_mem = harness.store.runs[run_id]

    async def copy_and_read():
        st = await setup()
        try:
            await st.save_run(run_mem)
            for ev in await harness.store.events(run_id):
                await st.append_event(ev)
            fresh = PostgresStore(pg)
            await fresh.open()
            try:
                got = await fresh.get_run(run_id)
                evs = await fresh.events(run_id)
            finally:
                await fresh.close()
        finally:
            await st.close()
        return got, evs

    got, evs = asyncio.run(copy_and_read())
    assert got.status == "done" and got.lanes["gemelo"].result.delivered
    assert evs[-1].type == "run.end"
