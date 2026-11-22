"""Filtraciones: atribución de lo que llega al atacante o a canarytokens.

El servidor atacante (P3) no conoce los valores: reenvía lo que recibe y aquí se
empareja contra los secretos activos, con sus codificaciones y capas anidadas.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING

from . import canary, scanner
from .models import Leak

if TYPE_CHECKING:
    from .runner import Orchestrator


log = logging.getLogger("aigis.leaks")


class LeakTracker:
    def __init__(self, orch: Orchestrator) -> None:
        self.orch = orch
        # Tokens de las últimas peticiones al atacante, para reconstruir llaves partidas
        self._recent: deque[tuple[float, list[str]]] = deque(maxlen=orch.settings.fragment_window_max)
        self._fragment_done: set[str] = set()
        self._triggered: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self.canary_transport = None  # tests: httpx.MockTransport

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
        if ref.pool == "A" and ref.canary_id and source == "attacker":
            self._schedule_canary(ref)
        return leak

    # ----- canary: usar la llave para que suene la alerta real -----

    def _schedule_canary(self, ref) -> None:
        if not self.orch.settings.canary_trigger or ref.canary_id in self._triggered:
            return
        self._triggered.add(ref.canary_id)
        t = asyncio.create_task(self.trigger_canary(ref))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def trigger_canary(self, ref) -> dict:
        secret = self.orch.registry.canary_secrets.get(ref.canary_id)
        data = {"canary_id": ref.canary_id, "secret_id": ref.id, "env_name": ref.env_name}
        if not secret:
            data["status"] = "no_secret"  # canaries.json sin `secret`: no se puede firmar
        else:
            try:
                data["http_status"] = await canary.use_key(ref.value, secret, self.orch.settings.canary_sts_url,
                                                           transport=self.canary_transport)
                data["status"] = "sent"
            except Exception as e:  # noqa: BLE001
                data["status"], data["error"] = "error", type(e).__name__
                log.warning("no se pudo usar la canary %s: %s", ref.canary_id, type(e).__name__)
        if ref.run_id:
            rc = self.orch.contexts.get(ref.run_id)
            await self.orch.bus.emit(ref.run_id, "canary.trigger", data, lane=ref.lane, role=ref.role,
                                     mode=rc.run.mode if rc else "live")
        return data

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
        self._fragment_done |= seen
        out += await self.scan_fragments(texts, channel=channel, source=source, at=at or time.time())
        return out

    def _live_secrets(self, now_: float) -> list:
        """Secretos de corridas en curso o que terminaron dentro de la ventana."""
        s = self.orch.settings
        out = []
        for rc in self.orch.contexts.values():
            ended = rc.run.ended_at.timestamp() if rc.run.ended_at else None
            if ended is None or now_ - ended <= s.fragment_window_s:
                out += self.orch.registry.for_run(rc.run.id)
        return out

    async def scan_fragments(self, texts: list[str], *, channel: str, source: str, at: float) -> list[Leak]:
        """Llave partida en varias peticiones: se juntan los trozos de las peticiones recientes.

        Solo cuenta si aportan al menos dos peticiones (una sola ya la cubre `scan_payload`) y
        cubren `fragment_coverage` del valor con trozos de `fragment_min_len` o más.
        """
        s = self.orch.settings
        live = [ref for ref in self._live_secrets(at) if ref.value]
        # Solo se guardan los tokens que podrían ser un trozo de algún secreto vivo: cortos y con
        # un n-grama en común. Así la ventana no crece con lo que mande cualquiera al sink, y
        # los blobs grandes no suman cobertura por azar.
        grams = scanner.ngrams([ref.value for ref in live], s.fragment_min_len)
        toks = scanner.tokens_of(texts)
        self._recent.append((at, scanner.candidate_tokens(toks, grams, s.fragment_min_len, s.fragment_token_max)))
        window = [t for ts, t in self._recent if at - ts <= s.fragment_window_s]
        pending = [ref for ref in live if ref.id not in self._fragment_done]
        if not pending or not any(window):
            return []

        def coverage() -> list[tuple[object, float, list[int]]]:
            return [(ref, *scanner.fragment_coverage(ref.value, window,
                                                     scanner.fragment_min_len(ref.value, s.fragment_min_len)))
                    for ref in pending]

        # SequenceMatcher es CPU pura: fuera del event loop, para no atrasar los hooks
        results = await asyncio.to_thread(coverage)
        out = []
        for ref, cov, contrib in results:
            if ref.id in self._fragment_done:
                continue
            if cov >= s.fragment_coverage and len(contrib) >= 2:
                self._fragment_done.add(ref.id)
                lk = await self.record(ref.run_id, ref.id, source=source, encoding=f"fragments:{len(contrib)}",
                                       channel=channel, at=at)
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
