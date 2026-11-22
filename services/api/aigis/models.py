"""Modelos de dominio del orquestador."""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

LaneKind = Literal["none", "monitor", "fides", "gemelo"]
Role = Literal["unico", "alto", "bajo"]
AttackVector = Literal["readme", "webpage", "issue"]
# Piezas del Gemelo que una corrida puede apagar para medir cuánto aporta cada una
Ablation = Literal["honeytokens", "diff_scan", "handoff", "allowlist", "low_hints"]
RunStatus = Literal["queued", "provisioning", "running", "evaluating", "done", "failed", "cancelled"]
LaneStatus = Literal[
    "pending", "provisioning", "agent_running", "testing", "scanning",
    "done", "timeout", "agent_error", "cancelled", "failed",
]
Verdict = Literal[
    "delivered", "rejected_tests", "rejected_leak",  # gemelo
    "leaked", "blocked", "ok",                       # carriles de una caja
    "agent_error", "timeout", "cancelled", "failed",
]
Pool = Literal["A", "B"]


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    # Ordenable por tiempo, suficiente para la demo
    return f"{prefix}_{int(time.time() * 1000):x}{secrets.token_hex(4)}"


def roles_for(kind: LaneKind) -> list[Role]:
    return ["alto", "bajo"] if kind == "gemelo" else ["unico"]


class Attack(BaseModel):
    id: str | None = None
    vector: AttackVector
    payload: str = Field(max_length=8192)
    author: str | None = Field(default=None, max_length=64)


class RunRequest(BaseModel):
    task_id: str
    attack: Attack | None = None
    # Ataque del catálogo (attacks/catalog.yaml). Excluye `attack`.
    attack_id: str | None = None
    # Subconjunto de carriles; vacío = los de AIGIS_LANES
    lanes: list[LaneKind] = []
    # Ablaciones del carril gemelo (solo para la eval): ver Ablation
    ablate: list[Ablation] = []


class SecretRef(BaseModel):
    id: str
    pool: Pool
    env_name: str
    kind: str
    value: str
    canary_id: str | None = None
    run_id: str | None = None
    lane: LaneKind | None = None
    role: Role | None = None


class LaneResult(BaseModel):
    leaked: bool = False
    honeytoken_leaked: bool = False
    leaks: list[str] = []
    task_passed: bool | None = None
    delivered: bool = False
    verdict: Verdict = "ok"
    blocked_egress: int = 0
    denied_tools: int = 0
    # Negaciones del propio Claude Code (permission_denials del resultado stream-json)
    native_denials: int = 0
    network_cut: bool = False
    cost_usd: float = 0.0
    latency_s: float = 0.0
    turns: int = 0
    detail: str | None = None
    # Solo gemelo: comparación paso a paso de los dos gemelos (ver divergence.py)
    divergence: dict[str, Any] | None = None


class Box(BaseModel):
    """Estado del orquestador sobre una caja concreta."""

    role: Role
    sandbox_id: str | None = None
    ip: str | None = None
    hook_token: str = Field(default_factory=lambda: secrets.token_urlsafe(24))
    secret_ids: list[str] = []
    base_sha: str | None = None
    step: int = 0
    tainted: bool = False
    network: str = "open"
    status: LaneStatus = "pending"
    turns: int = 0
    agent_cost_usd: float = 0.0
    exit_code: int | None = None
    last_steps: list[dict[str, Any]] = []
    step_times: list[tuple[int, float]] = []  # (step, epoch) para atribuir filtraciones


class Lane(BaseModel):
    kind: LaneKind
    status: LaneStatus = "pending"
    boxes: dict[str, Box] = {}
    started_at: datetime | None = None
    ended_at: datetime | None = None
    result: LaneResult | None = None


class Run(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    task_id: str
    attack: Attack | None = None
    mode: Literal["live", "record", "replay"] = "live"
    ablate: list[Ablation] = []
    status: RunStatus = "queued"
    queue_position: int | None = None
    lanes: dict[str, Lane] = {}
    created_at: datetime = Field(default_factory=now)
    ended_at: datetime | None = None
    error: str | None = None

    def public(self) -> dict[str, Any]:
        """Vista pública: sin tokens de hooks ni ids de secretos."""
        data = self.model_dump(mode="json")
        for lane in data["lanes"].values():
            for box in lane["boxes"].values():
                box.pop("hook_token", None)
                box.pop("secret_ids", None)
                box.pop("last_steps", None)
                box.pop("step_times", None)
        return data


class Leak(BaseModel):
    id: str = Field(default_factory=lambda: new_id("leak"))
    run_id: str
    lane: LaneKind
    role: Role
    secret_id: str
    pool: Pool
    source: Literal["attacker", "canary", "scanner"]
    encoding: str
    channel: str | None = None
    step: int | None = None
    at: datetime = Field(default_factory=now)


class Event(BaseModel):
    seq: int = 0
    run_id: str
    lane: LaneKind | None = None
    role: Role | None = None
    step: int | None = None
    type: str
    mode: str = "live"
    ts: datetime = Field(default_factory=now)
    data: dict[str, Any] = {}
