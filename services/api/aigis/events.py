"""Bus de eventos por corrida: asigna seq, persiste, reparte a suscriptores SSE.

Todo evento pasa por `redact` antes de salir: ningún valor de secreto registrado
llega a la web ni a la base de eventos.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from .models import Event, LaneKind, Role
from .store import Store

Redactor = Callable[[str, str], str]  # (run_id, texto) -> texto redactado


class EventBus:
    def __init__(self, store: Store, redactor: Redactor | None = None) -> None:
        self.store = store
        self.redactor = redactor
        self._seq: dict[str, int] = {}
        self._subs: dict[str, set[asyncio.Queue[Event | None]]] = {}
        self._lock = asyncio.Lock()

    def _redact_data(self, run_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.redactor:
            return data
        raw = json.dumps(data, ensure_ascii=False, default=str)
        clean = self.redactor(run_id, raw)
        return data if clean == raw else json.loads(clean)

    async def emit(
        self,
        run_id: str,
        type: str,
        data: dict[str, Any] | None = None,
        *,
        lane: LaneKind | None = None,
        role: Role | None = None,
        step: int | None = None,
        mode: str = "live",
    ) -> Event:
        async with self._lock:
            seq = self._seq.get(run_id, 0) + 1
            self._seq[run_id] = seq
            ev = Event(
                seq=seq, run_id=run_id, lane=lane, role=role, step=step, type=type, mode=mode,
                data=self._redact_data(run_id, data or {}),
            )
            await self.store.append_event(ev)
        for q in list(self._subs.get(run_id, ())):
            q.put_nowait(ev)
        return ev

    async def close(self, run_id: str) -> None:
        """Avisa a los suscriptores que la corrida terminó."""
        for q in list(self._subs.get(run_id, ())):
            q.put_nowait(None)

    async def subscribe(self, run_id: str, after_seq: int = 0, follow: bool = True) -> AsyncIterator[Event]:
        q: asyncio.Queue[Event | None] = asyncio.Queue()
        self._subs.setdefault(run_id, set()).add(q)
        try:
            last = after_seq
            for ev in await self.store.events(run_id, after_seq):
                last = ev.seq
                yield ev
            if not follow:
                return
            while True:
                ev = await q.get()
                if ev is None:
                    return
                if ev.seq <= last:
                    continue
                last = ev.seq
                yield ev
        finally:
            self._subs.get(run_id, set()).discard(q)
