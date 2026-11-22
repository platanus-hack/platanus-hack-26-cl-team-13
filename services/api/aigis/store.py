"""Persistencia de corridas y resultados.

`Store` es la interfaz que usa el orquestador. `MemoryStore` sirve para F0 y F1;
P3 agrega `PostgresStore` con las mismas firmas. El orquestador no conoce SQL.
"""

from __future__ import annotations

from typing import Protocol

from .models import Event, Leak, Run, SecretRef


class Store(Protocol):
    async def save_run(self, run: Run) -> None: ...
    async def get_run(self, run_id: str) -> Run | None: ...
    async def list_runs(self, limit: int = 50) -> list[Run]: ...
    async def append_event(self, ev: Event) -> None: ...
    async def events(self, run_id: str, after_seq: int = 0) -> list[Event]: ...
    async def save_secret(self, ref: SecretRef) -> None: ...
    async def secrets_for_run(self, run_id: str) -> list[SecretRef]: ...
    async def save_leak(self, leak: Leak) -> None: ...
    async def leaks_for_run(self, run_id: str) -> list[Leak]: ...
    async def save_diff(self, run_id: str, lane: str, role: str, diff: str) -> None: ...
    async def get_diff(self, run_id: str, lane: str, role: str) -> str | None: ...
    async def save_usage(self, run_id: str, usage: dict) -> None: ...
    async def get_usage(self, run_id: str) -> dict | None: ...
    # Gasto real acumulado (lo que reportó el gateway por corrida, monitor incluido)
    async def total_cost(self) -> tuple[float, int]: ...


class MemoryStore:
    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}
        self._events: dict[str, list[Event]] = {}
        self.secrets: dict[str, SecretRef] = {}
        self.leaks: dict[str, Leak] = {}
        self.diffs: dict[tuple[str, str, str], str] = {}
        self.usage: dict[str, dict] = {}

    async def save_run(self, run: Run) -> None:
        self.runs[run.id] = run

    async def get_run(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    async def list_runs(self, limit: int = 50) -> list[Run]:
        return sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True)[:limit]

    async def append_event(self, ev: Event) -> None:
        self._events.setdefault(ev.run_id, []).append(ev)

    async def events(self, run_id: str, after_seq: int = 0) -> list[Event]:
        return [e for e in self._events.get(run_id, []) if e.seq > after_seq]

    async def save_secret(self, ref: SecretRef) -> None:
        self.secrets[ref.id] = ref

    async def secrets_for_run(self, run_id: str) -> list[SecretRef]:
        return [s for s in self.secrets.values() if s.run_id == run_id]

    async def save_leak(self, leak: Leak) -> None:
        self.leaks[leak.id] = leak

    async def leaks_for_run(self, run_id: str) -> list[Leak]:
        return [lk for lk in self.leaks.values() if lk.run_id == run_id]

    async def save_diff(self, run_id: str, lane: str, role: str, diff: str) -> None:
        self.diffs[(run_id, lane, role)] = diff

    async def get_diff(self, run_id: str, lane: str, role: str) -> str | None:
        return self.diffs.get((run_id, lane, role))

    async def save_usage(self, run_id: str, usage: dict) -> None:
        self.usage[run_id] = usage

    async def get_usage(self, run_id: str) -> dict | None:
        return self.usage.get(run_id)

    async def total_cost(self) -> tuple[float, int]:
        return sum(float(u.get("cost_usd") or 0.0) for u in self.usage.values()), len(self.usage)
