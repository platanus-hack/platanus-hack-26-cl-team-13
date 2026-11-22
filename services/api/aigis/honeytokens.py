"""Generación y registro de secretos por caja.

- Pool A (honeytokens): solo para el gemelo alto. Si existe `secrets/canaries.json`
  (P3, ignorado por git) se toman canary tokens de ahí; si no, se generan propios.
- Pool B (sintéticos): para el gemelo bajo y los carriles de una caja. Formato real,
  valor falso. Nunca credenciales reales (D2).

Cada caja recibe valores únicos, así cualquier aparición se atribuye a una sola
corrida, carril y gemelo.

Formato de `tasks/<id>/secrets.template`: una línea `NOMBRE=tipo` por secreto,
con `#` para comentarios. Tipos: stripe, aws_access_key, aws_secret_key, github,
anthropic, openai, slack, generic.
"""

from __future__ import annotations

import json
import secrets
import string
from pathlib import Path

from .models import LaneKind, Pool, Role, SecretRef, new_id

_ALNUM = string.ascii_letters + string.digits
_UPPER_DIG = string.ascii_uppercase + string.digits
_B64 = string.ascii_letters + string.digits + "+/"


def _r(alphabet: str, n: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


GENERATORS = {
    "stripe": lambda: "sk_live_" + _r(_ALNUM, 24),
    "aws_access_key": lambda: "AKIA" + _r(_UPPER_DIG, 16),
    "aws_secret_key": lambda: _r(_B64, 40),
    "github": lambda: "ghp_" + _r(_ALNUM, 36),
    "anthropic": lambda: "sk-ant-api03-" + _r(_ALNUM + "-_", 80),
    "openai": lambda: "sk-proj-" + _r(_ALNUM, 48),
    "slack": lambda: "xoxb-" + _r(string.digits, 12) + "-" + _r(string.digits, 12) + "-" + _r(_ALNUM, 24),
    "generic": lambda: secrets.token_hex(16),
}


def parse_template(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, kind = line.partition("=")
        kind = kind.strip() or "generic"
        if kind not in GENERATORS:
            raise ValueError(f"tipo de secreto desconocido: {kind}")
        out.append((name.strip(), kind))
    return out


def infer_kind(env_name: str) -> str:
    n = env_name.upper()
    if "STRIPE" in n:
        return "stripe"
    if n == "AWS_ACCESS_KEY_ID":
        return "aws_access_key"
    if n == "AWS_SECRET_ACCESS_KEY":
        return "aws_secret_key"
    if "GITHUB" in n or "GH_" in n:
        return "github"
    if "ANTHROPIC" in n:
        return "anthropic"
    if "OPENAI" in n:
        return "openai"
    if "SLACK" in n:
        return "slack"
    return "generic"


class SecretRegistry:
    """Valores activos de todas las corridas en curso, para escanear y redactar."""

    def __init__(self, canaries_path: Path | None = None) -> None:
        self.by_id: dict[str, SecretRef] = {}
        self._canaries: list[dict] = []
        self._used_canaries: set[str] = set()
        # canary_id -> secreto pareado (AWS_SECRET_ACCESS_KEY), para poder usar la llave (canary.py)
        self.canary_secrets: dict[str, str] = {}
        if canaries_path and canaries_path.exists():
            self._canaries = json.loads(canaries_path.read_text("utf-8"))

    def _take_canary(self, env_name: str, kind: str) -> dict | None:
        for c in self._canaries:
            cid = c.get("canary_id") or c.get("id")
            if cid in self._used_canaries:
                continue
            if c.get("env_name") == env_name or c.get("kind") == kind:
                self._used_canaries.add(cid)
                return c
        return None

    def assign(self, run_id: str, lane: LaneKind, role: Role, spec: list[tuple[str, str]]) -> list[SecretRef]:
        pool: Pool = "A" if role == "alto" else "B"
        refs = []
        canaries = [self._take_canary(env_name, kind) if pool == "A" else None for env_name, kind in spec]
        # Una canary de AWS trae su secret key: va en la AWS_SECRET_ACCESS_KEY de la misma caja,
        # así el par es válido y el orquestador puede usarlo para disparar la alerta
        paired = next((c for c in canaries if c and c.get("secret")), None)
        for (env_name, kind), canary in zip(spec, canaries):
            value = canary["value"] if canary else None
            if value is None and paired and kind == "aws_secret_key":
                value = paired["secret"]
                self.canary_secrets[paired.get("canary_id") or paired.get("id")] = value
                paired = None
            ref = SecretRef(
                id=new_id("sec"),
                pool=pool,
                env_name=env_name,
                kind=kind,
                value=value or GENERATORS[kind](),
                canary_id=(canary.get("canary_id") or canary.get("id")) if canary else None,
                run_id=run_id,
                lane=lane,
                role=role,
            )
            self.by_id[ref.id] = ref
            refs.append(ref)
        return refs

    def for_run(self, run_id: str) -> list[SecretRef]:
        return [s for s in self.by_id.values() if s.run_id == run_id]

    def pairs(self, run_id: str | None = None, pool: Pool | None = None) -> list[tuple[str, str]]:
        return [
            (s.id, s.value)
            for s in self.by_id.values()
            if (run_id is None or s.run_id == run_id) and (pool is None or s.pool == pool)
        ]

    def by_canary(self, canary_id: str) -> SecretRef | None:
        return next((s for s in self.by_id.values() if s.canary_id == canary_id), None)

    def release(self, run_id: str) -> None:
        """No se borra al terminar: las alertas de canary llegan minutos después."""
        return None


def dotenv(refs: list[SecretRef]) -> str:
    return "".join(f"{r.env_name}={r.value}\n" for r in refs)
