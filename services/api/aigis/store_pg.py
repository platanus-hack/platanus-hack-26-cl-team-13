"""Store sobre Postgres (Render Postgres por red privada). Mismas firmas que `MemoryStore`.

Mínimo a propósito: cada objeto se guarda como JSONB con las columnas por las que se
consulta. P3 puede normalizar después sin cambiar al orquestador.

Se activa con `DATABASE_URL` (Render la inyecta desde el blueprint). Los valores de
secretos que se guardan son sintéticos (pool B) o honeytokens (pool A), nunca reales.
"""

from __future__ import annotations

import json

import asyncpg

from .models import Event, Leak, Run, SecretRef

log = __import__("logging").getLogger("aigis.store_pg")

SCHEMA = """
create table if not exists aigis_runs (
  id text primary key,
  created_at timestamptz not null,
  status text not null,
  data jsonb not null
);
create index if not exists aigis_runs_created on aigis_runs (created_at desc);
create table if not exists aigis_events (
  run_id text not null,
  seq integer not null,
  type text not null,
  data jsonb not null,
  primary key (run_id, seq)
);
create table if not exists aigis_secrets (
  id text primary key,
  run_id text,
  data jsonb not null
);
create index if not exists aigis_secrets_run on aigis_secrets (run_id);
create table if not exists aigis_leaks (
  id text primary key,
  run_id text not null,
  data jsonb not null
);
create index if not exists aigis_leaks_run on aigis_leaks (run_id);
create table if not exists aigis_diffs (
  run_id text not null,
  lane text not null,
  role text not null,
  diff text not null,
  primary key (run_id, lane, role)
);
create table if not exists aigis_usage (
  run_id text primary key,
  data jsonb not null
);
"""


def _j(model) -> str:
    return model.model_dump_json()


def _load(v):
    return json.loads(v) if isinstance(v, str) else v


class PostgresStore:
    # asyncpg y no psycopg: funciona con el event loop por defecto de Windows (Proactor),
    # que el orquestador necesita para lanzar subprocesos.
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 5) -> None:
        self.dsn, self.min_size, self.max_size = dsn, min_size, max_size
        self.pool: asyncpg.Pool | None = None

    async def open(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=self.min_size, max_size=self.max_size, timeout=30)
        await self.pool.execute(SCHEMA)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def save_run(self, run: Run) -> None:
        await self.pool.execute(
            "insert into aigis_runs (id, created_at, status, data) values ($1, $2, $3, $4::jsonb) "
            "on conflict (id) do update set status = excluded.status, data = excluded.data",
            run.id, run.created_at, run.status, _j(run))

    async def get_run(self, run_id: str) -> Run | None:
        v = await self.pool.fetchval("select data from aigis_runs where id = $1", run_id)
        return Run.model_validate(_load(v)) if v else None

    async def list_runs(self, limit: int = 50) -> list[Run]:
        rows = await self.pool.fetch("select data from aigis_runs order by created_at desc limit $1", limit)
        out = []
        for r in rows:
            try:
                out.append(Run.model_validate(_load(r["data"])))
            except Exception as e:  # noqa: BLE001
                # Una corrida corrupta (p. ej. interrumpida a mitad por un crash) no debe
                # tirar el listado completo: se omite y se loguea.
                log.warning("run corrupto omitido en list_runs: %s", e)
        return out

    async def append_event(self, ev: Event) -> None:
        await self.pool.execute(
            "insert into aigis_events (run_id, seq, type, data) values ($1, $2, $3, $4::jsonb) on conflict do nothing",
            ev.run_id, ev.seq, ev.type, _j(ev))

    async def events(self, run_id: str, after_seq: int = 0) -> list[Event]:
        rows = await self.pool.fetch(
            "select data from aigis_events where run_id = $1 and seq > $2 order by seq", run_id, after_seq)
        return [Event.model_validate(_load(r["data"])) for r in rows]

    async def save_secret(self, ref: SecretRef) -> None:
        await self.pool.execute(
            "insert into aigis_secrets (id, run_id, data) values ($1, $2, $3::jsonb) on conflict (id) do nothing",
            ref.id, ref.run_id, _j(ref))

    async def secrets_for_run(self, run_id: str) -> list[SecretRef]:
        rows = await self.pool.fetch("select data from aigis_secrets where run_id = $1", run_id)
        return [SecretRef.model_validate(_load(r["data"])) for r in rows]

    async def save_leak(self, leak: Leak) -> None:
        await self.pool.execute(
            "insert into aigis_leaks (id, run_id, data) values ($1, $2, $3::jsonb) on conflict (id) do nothing",
            leak.id, leak.run_id, _j(leak))

    async def leaks_for_run(self, run_id: str) -> list[Leak]:
        rows = await self.pool.fetch("select data from aigis_leaks where run_id = $1", run_id)
        return [Leak.model_validate(_load(r["data"])) for r in rows]

    async def save_diff(self, run_id: str, lane: str, role: str, diff: str) -> None:
        await self.pool.execute(
            "insert into aigis_diffs (run_id, lane, role, diff) values ($1, $2, $3, $4) "
            "on conflict (run_id, lane, role) do update set diff = excluded.diff",
            run_id, lane, role, diff)

    async def get_diff(self, run_id: str, lane: str, role: str) -> str | None:
        return await self.pool.fetchval(
            "select diff from aigis_diffs where run_id = $1 and lane = $2 and role = $3", run_id, lane, role)

    async def save_usage(self, run_id: str, usage: dict) -> None:
        await self.pool.execute(
            "insert into aigis_usage (run_id, data) values ($1, $2::jsonb) "
            "on conflict (run_id) do update set data = excluded.data",
            run_id, json.dumps(usage))

    async def get_usage(self, run_id: str) -> dict | None:
        v = await self.pool.fetchval("select data from aigis_usage where run_id = $1", run_id)
        return _load(v) if v else None

    async def total_cost(self) -> tuple[float, int]:
        row = await self.pool.fetchrow(
            "select coalesce(sum((data->>'cost_usd')::float), 0) as spent, count(*) as n from aigis_usage")
        return float(row["spent"]), int(row["n"])
