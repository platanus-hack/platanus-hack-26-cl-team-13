"""Tokens por corrida o por caja, con expiración, revocación y tope en USD (D4).

Solo se guarda el sha256 del token: un volcado de memoria o de logs no sirve para
llamar al modelo. El gasto se controla con reservas: antes de reenviar una llamada se
reserva su peor caso y al terminar se reemplaza por el costo real. Así varias llamadas
en paralelo no pueden pasar el tope entre todas.

En memoria: un reinicio del servicio invalida los tokens vivos (las corridas en curso
terminan con 401). Persistir en Postgres queda para cuando exista store/postgres.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
from dataclasses import dataclass, field

from .pricing import Usage

TOKEN_PREFIX = "gw_"
_LANE_RE = re.compile(r"^[a-z0-9_-]{1,32}(/[a-z0-9_-]{1,32})?$")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_lane(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    return v if _LANE_RE.match(v) else "unknown"


@dataclass
class LaneUsage:
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    requests: int = 0

    def add(self, u: Usage, cost: float) -> None:
        self.cost_usd += cost
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.cache_creation_input_tokens += u.cache_creation_input_tokens
        self.cache_read_input_tokens += u.cache_read_input_tokens
        self.requests += 1

    def as_dict(self) -> dict:
        return {"cost_usd": round(self.cost_usd, 6), "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_creation_input_tokens": self.cache_creation_input_tokens,
                "cache_read_input_tokens": self.cache_read_input_tokens, "requests": self.requests}


@dataclass
class TokenRecord:
    key: str
    run_id: str
    budget_usd: float
    expires_at: float
    lane: str | None = None  # si viene fijado, el header X-Aigis-Lane se ignora
    created_at: float = field(default_factory=time.time)
    revoked_at: float | None = None
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    requests: int = 0
    in_flight: int = 0
    by_lane: dict[str, LaneUsage] = field(default_factory=dict)
    cut: str | None = None  # razón del último rechazo por tope (budget | requests)

    def state(self, now: float) -> str:
        if self.revoked_at is not None:
            return "revoked"
        if now >= self.expires_at:
            return "expired"
        return "active"

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.spent_usd - self.reserved_usd)

    def usage(self, now: float) -> dict:
        total = LaneUsage()
        for lu in self.by_lane.values():
            total.cost_usd += lu.cost_usd
            total.input_tokens += lu.input_tokens
            total.output_tokens += lu.output_tokens
            total.cache_creation_input_tokens += lu.cache_creation_input_tokens
            total.cache_read_input_tokens += lu.cache_read_input_tokens
            total.requests += lu.requests
        return {
            "run_id": self.run_id, "lane": self.lane, "state": self.state(now),
            "budget_usd": self.budget_usd, "remaining_usd": round(self.remaining_usd, 6),
            "expires_at": self.expires_at, "cut": self.cut,
            **total.as_dict(),
            "cost_usd": round(self.spent_usd, 6),
            "by_lane": {k: v.as_dict() for k, v in sorted(self.by_lane.items())},
        }


class Denied(Exception):
    def __init__(self, status: int, kind: str, message: str) -> None:
        super().__init__(message)
        self.status, self.kind, self.message = status, kind, message


@dataclass
class Reservation:
    rec: TokenRecord
    lane: str
    amount: float
    settled: bool = False


class TokenStore:
    def __init__(self, retain_s: int = 24 * 3600, clock=time.time) -> None:
        self._by_key: dict[str, TokenRecord] = {}
        self._lock = asyncio.Lock()
        self.retain_s = retain_s
        self.clock = clock

    async def issue(self, run_id: str, budget_usd: float, ttl_s: int, lane: str | None = None) -> tuple[str, TokenRecord]:
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        now = self.clock()
        rec = TokenRecord(key=digest(token), run_id=run_id, budget_usd=budget_usd,
                          expires_at=now + ttl_s, lane=lane, created_at=now)
        async with self._lock:
            self._purge(now)
            self._by_key[rec.key] = rec
        return token, rec

    def get(self, token: str) -> TokenRecord | None:
        return self._by_key.get(digest(token)) if token else None

    def by_run(self, run_id: str) -> list[TokenRecord]:
        return [r for r in self._by_key.values() if r.run_id == run_id]

    async def revoke(self, token: str) -> bool:
        rec = self.get(token)
        if rec is None:
            return False
        async with self._lock:
            if rec.revoked_at is None:
                rec.revoked_at = self.clock()
        return True

    async def revoke_run(self, run_id: str) -> int:
        async with self._lock:
            n = 0
            for rec in self.by_run(run_id):
                if rec.revoked_at is None:
                    rec.revoked_at = self.clock()
                    n += 1
            return n

    def authenticate(self, token: str) -> TokenRecord:
        rec = self.get(token)
        if rec is None:
            raise Denied(401, "authentication_error", "token del gateway inválido")
        st = rec.state(self.clock())
        if st != "active":
            raise Denied(401, "authentication_error", f"token del gateway {'revocado' if st == 'revoked' else 'expirado'}")
        return rec

    async def reserve(self, rec: TokenRecord, lane: str, amount: float, max_requests: int) -> Reservation:
        """Reserva `amount` USD o rechaza. Revisa estado otra vez bajo el lock."""
        async with self._lock:
            if rec.state(self.clock()) != "active":
                raise Denied(401, "authentication_error", "token del gateway revocado o expirado")
            if max_requests and rec.requests >= max_requests:
                rec.cut = "requests"
                raise Denied(403, "permission_error", f"tope de {max_requests} llamadas al modelo alcanzado")
            if amount > rec.remaining_usd:
                rec.cut = "budget"
                raise Denied(402, "billing_error",
                             f"tope de gasto del token alcanzado (USD {rec.budget_usd:.2f})")
            rec.reserved_usd += amount
            rec.requests += 1
            rec.in_flight += 1
            return Reservation(rec, lane, amount)

    async def settle(self, res: Reservation, usage: Usage | None, cost: float | None) -> None:
        """Cierra la reserva. Sin costo conocido (stream cortado) se cobra la reserva entera."""
        if res.settled:
            return
        async with self._lock:
            res.settled = True
            rec = res.rec
            rec.reserved_usd = max(0.0, rec.reserved_usd - res.amount)
            rec.in_flight -= 1
            charged = res.amount if cost is None else cost
            rec.spent_usd += charged
            rec.by_lane.setdefault(res.lane, LaneUsage()).add(usage or Usage(), charged)

    async def release(self, res: Reservation) -> None:
        """Libera una reserva de una llamada que el upstream rechazó sin generar nada."""
        if res.settled:
            return
        async with self._lock:
            res.settled = True
            res.rec.reserved_usd = max(0.0, res.rec.reserved_usd - res.amount)
            res.rec.in_flight -= 1
            res.rec.requests -= 1

    def _purge(self, now: float) -> None:
        dead = [k for k, r in self._by_key.items()
                if r.state(now) != "active" and r.in_flight == 0
                and now - (r.revoked_at or r.expires_at) > self.retain_s]
        for k in dead:
            del self._by_key[k]
