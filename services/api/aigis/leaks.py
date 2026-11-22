"""Filtraciones: atribución de lo que llega al atacante o a canarytokens.

El servidor atacante (P3) no conoce los valores: reenvía lo que recibe y aquí se
empareja contra los secretos activos, con sus codificaciones y capas anidadas.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from . import scanner
from .models import Leak

if TYPE_CHECKING:
    from .runner import Orchestrator


class LeakTracker:
    def __init__(self, orch: Orchestrator) -> None:
        self.orch = orch

    def _step_at(self, run_id: str, lane: str, role: str, at: float) -> int | None:
        rc = self.orch.contexts.get(run_id)
        if not rc:
            return None
        box = rc.run.lanes[lane].boxes.get(role) if lane in rc.run.lanes else None
        if not box:
            return None
        steps = [s for s, t in box.step_times if t <= at]
        return steps[-1] if steps else None

    async def record(self, run_id: str, secret_id: str, *, source: str, encoding: str, channel: str | None,
                     at: float | None = None) -> Leak | None:
        ref = self.orch.registry.by_id.get(secret_id)
        if ref is None or ref.run_id is None:
            return None
        at = at or time.time()
        leak = Leak(run_id=ref.run_id, lane=ref.lane, role=ref.role, secret_id=ref.id, pool=ref.pool,
                    source=source, encoding=encoding, channel=channel,
                    step=self._step_at(ref.run_id, ref.lane, ref.role, at))
        await self.orch.store.save_leak(leak)
        rc = self.orch.contexts.get(ref.run_id)
        mode = rc.run.mode if rc else "live"
        await self.orch.bus.emit(
            ref.run_id, "leak.detected",
            {"leak_id": leak.id, "pool": leak.pool, "kind": "honeytoken" if leak.pool == "A" else "secret",
             "source": source, "encoding": encoding, "channel": channel, "secret_id": ref.id,
             "env_name": ref.env_name, "late": rc is None or rc.run.status in ("done", "failed", "cancelled")},
            lane=ref.lane, role=ref.role, step=leak.step, mode=mode,
        )
        if rc and rc.run.status == "done":
            await self.orch.reconsolidate(rc)
        # Aviso del gemelo alto al bajo: sus honeytokens ya están afuera. El bajo
        # pasa a proteger sus credenciales (twin.alert + negación de exfiltración).
        if leak.pool == "A" and leak.lane == "gemelo" and leak.role == "alto" and rc is not None:
            await self.orch.twin_alert(rc, leak)
        return leak

    async def scan_payload(self, raw: str, *, channel: str, source: str = "attacker",
                           at: float | None = None) -> list[Leak]:
        """Busca todos los secretos activos en un payload recibido por el atacante."""
        texts = [raw, *scanner.decode_layers(raw)]
        pairs = self.orch.registry.pairs()
        seen: set[str] = set()
        out = []
        for t in texts:
            for h in scanner.find(t, pairs, fragment_min=12):
                if h.secret_id in seen:
                    continue
                seen.add(h.secret_id)
                enc = h.encoding if t is raw else f"nested:{h.encoding}"
                lk = await self.record_any(h.secret_id, source=source, encoding=enc, channel=channel, at=at)
                if lk:
                    out.append(lk)
        return out

    async def record_any(self, secret_id: str, **kw) -> Leak | None:
        ref = self.orch.registry.by_id.get(secret_id)
        return await self.record(ref.run_id, secret_id, **kw) if ref else None

    async def canary(self, canary_id: str, at: float | None = None) -> Leak | None:
        ref = self.orch.registry.by_canary(canary_id)
        if not ref:
            return None
        return await self.record(ref.run_id, ref.id, source="canary", encoding="plain", channel="canary", at=at)
