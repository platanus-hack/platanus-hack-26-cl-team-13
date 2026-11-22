"""Acceso de jueces: tokens cortos por juez, topes y la vista pública de corridas.

Token = "<alias>-<firma>": la firma es HMAC(AIGIS_JUDGE_SECRET, alias) en base32 corto, así
que no hay tabla que guardar ni que se pierda en un reinicio y se puede dictar o copiar
desde un link. Revocar un juez = ponerlo en AIGIS_JUDGE_REVOKED; revocar todos = cambiar
el secreto.

Lo que manda un juez es dato no confiable: solo se escribe en el vector (README, issue o
página) dentro de las cajas. No elige carriles, modelo ni turnos.

La vista pública (`public_run`, `public_event`) sale de una lista blanca de campos: veredictos,
herramientas, estados y filtraciones, sin ids de caja, URLs internas, prompts, diffs ni valores.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from typing import Any

from .config import Settings
from .models import Event, Run

ALIAS_RE = re.compile(r"^[a-z0-9]{2,16}$")
TOKEN_RE = re.compile(r"^([a-z0-9]{2,16})-([a-z2-7]{10})$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL = re.compile(r"https?://[^\s\"'<>)]+")
JUDGE_PREFIX = "judge:"
ACTIVE = ("queued", "provisioning", "running", "evaluating")


def sign(secret: str, alias: str) -> str:
    mac = hmac.new(secret.encode(), alias.encode(), hashlib.sha256).digest()
    return base64.b32encode(mac).decode().lower()[:10]


def make_token(secret: str, alias: str) -> str:
    alias = alias.strip().lower()
    if not ALIAS_RE.match(alias):
        raise ValueError("alias: 2 a 16 letras minúsculas o dígitos")
    return f"{alias}-{sign(secret, alias)}"


def check_token(settings: Settings, token: str) -> str | None:
    """Alias del juez si el token es válido, None si no."""
    if not settings.judge_secret:
        return None
    m = TOKEN_RE.match(token.strip().lower())
    if not m:
        return None
    alias, sig = m.groups()
    if alias in settings.judge_revoked_list:
        return None
    return alias if hmac.compare_digest(sig, sign(settings.judge_secret, alias)) else None


def clean_payload(text: str) -> str:
    """Quita caracteres de control (salvo tab y saltos) y normaliza saltos de línea."""
    return _CTRL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def author_alias(run: Run) -> str | None:
    a = run.attack.author if run.attack else None
    return a.removeprefix(JUDGE_PREFIX) if a and a.startswith(JUDGE_PREFIX) else None


class JudgeDesk:
    """Topes y ritmo de envío de los jueces. En memoria: un reinicio libera el ritmo,
    pero las cuotas se cuentan sobre las corridas guardadas, así que no se reinician."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.last_submit: dict[str, float] = {}
        self.paused = not settings.judges_enabled

    @staticmethod
    def spent(runs: list[Run]) -> float:
        return round(sum(lane.result.cost_usd for r in runs for lane in r.lanes.values() if lane.result), 4)

    def status(self, alias: str, runs: list[Run]) -> dict[str, Any]:
        mine = [r for r in runs if author_alias(r) == alias]
        wait = self.s.judge_min_interval_s - (time.time() - self.last_submit.get(alias, 0))
        return {
            "alias": alias,
            "runs_used": len(mine),
            "runs_max": self.s.judge_max_runs,
            "active_run": next((r.id for r in mine if r.status in ACTIVE), None),
            "wait_s": max(0, int(wait)),
            "spent_usd": self.spent(mine),
            "open": not self.paused,
        }

    def check(self, alias: str, runs: list[Run]) -> None:
        """Lanza ValueError con un mensaje para el juez si no puede enviar ahora."""
        if self.paused:
            raise ValueError("los envíos de jueces están en pausa")
        st = self.status(alias, runs)
        if st["active_run"]:
            raise ValueError(f"ya tienes una corrida en curso ({st['active_run']})")
        if st["runs_used"] >= self.s.judge_max_runs:
            raise ValueError(f"usaste tus {self.s.judge_max_runs} corridas")
        if st["wait_s"] > 0:
            raise ValueError(f"espera {st['wait_s']} s antes del próximo envío")
        judged = [r for r in runs if author_alias(r)]
        if len(judged) >= self.s.judge_total_runs:
            raise ValueError("se acabó el cupo de corridas de jueces del evento")
        if sum(r.status == "queued" for r in judged) >= self.s.judge_queue_max:
            raise ValueError("la cola está llena, prueba en unos minutos")
        if self.spent(judged) + self.s.run_budget_usd > self.s.judge_total_budget_usd:
            raise ValueError("se acabó el presupuesto de jueces del evento")

    def mark(self, alias: str) -> None:
        self.last_submit[alias] = time.time()


# ----- vista pública -----------------------------------------------------------------

_RESULT_KEYS = ("leaked", "honeytoken_leaked", "task_passed", "delivered", "verdict", "blocked_egress",
                "denied_tools", "native_denials", "network_cut", "cost_usd", "latency_s", "turns")
_BOX_KEYS = ("role", "status", "network", "turns", "tainted", "step")


class Scrubber:
    """Reemplaza las URLs internas que podrían aparecer en texto del agente o de herramientas."""

    def __init__(self, settings: Settings) -> None:
        self.attacker = settings.attacker_url_sandbox.rstrip("/")
        self.internal = [u.rstrip("/") for u in (settings.gateway_url_sandbox, settings.hook_base_sandbox,
                                                 settings.public_base_url, settings.gateway_url,
                                                 settings.sandbox_host_url) if u]

    def __call__(self, text: str) -> str:
        if self.attacker:
            text = text.replace(self.attacker, "{ATTACKER_URL}")
        for u in self.internal:
            text = text.replace(u, "{AIGIS}")

        def url(m: re.Match) -> str:
            v = m.group(0)
            return v if v.startswith("{") else re.sub(r"^(https?://[^/]+).*$", r"\1/…", v)

        return _URL.sub(url, text)


def public_attack(run: Run, scrub: Scrubber, preview: int) -> dict | None:
    if not run.attack:
        return None
    a = run.attack
    alias = author_alias(run)
    return {
        "id": a.id,
        "vector": a.vector,
        "author": alias or ("catálogo" if a.author == "catalog" else "equipo"),
        "judge": alias is not None,
        "payload": scrub(a.payload[:preview]) + ("…" if len(a.payload) > preview else "") if preview else "",
    }


def public_run(run: Run, scrub: Scrubber, preview: int = 600) -> dict[str, Any]:
    lanes = {}
    for k, lane in run.lanes.items():
        lanes[k] = {
            "kind": lane.kind, "status": lane.status,
            "started_at": lane.started_at.isoformat() if lane.started_at else None,
            "ended_at": lane.ended_at.isoformat() if lane.ended_at else None,
            "boxes": {r: {key: getattr(b, key) for key in _BOX_KEYS} for r, b in lane.boxes.items()},
            "result": ({key: getattr(lane.result, key) for key in _RESULT_KEYS} | {"leaks": [], "detail": None})
            if lane.result else None,
        }
    return {
        "id": run.id, "task_id": run.task_id, "mode": run.mode, "status": run.status,
        "queue_position": run.queue_position, "created_at": run.created_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "error": "error interno" if run.error else None,
        "attack": public_attack(run, scrub, preview),
        "lanes": lanes,
    }


def _pick(d: dict, *keys: str) -> dict:
    return {k: d[k] for k in keys if k in d}


def public_event(ev: Event, scrub: Scrubber) -> dict | None:
    """Evento recortado para la vista pública, o None si no se publica."""
    d = ev.data or {}
    t = ev.type
    if t == "run.status":
        data = _pick(d, "status", "queue_position")
    elif t == "run.start":
        data = _pick(d, "task_id", "lanes")
    elif t in ("lane.status", "run.end"):
        data = _pick(d, "status")
    elif t == "sandbox.ready":
        data = _pick(d, "network", "pool") | {"secrets": list(d.get("secrets") or [])}
    elif t == "agent.text":
        data = {"text": scrub(str(d.get("text", ""))[:1500])}
    elif t == "agent.end":
        data = _pick(d, "status", "turns")
    elif t == "tool.pre":
        inp = d.get("input")
        data = _pick(d, "tool", "decision") | {"input": scrub(str(inp)[:400]) if inp is not None else None}
        if d.get("reason"):
            data["reason"] = scrub(str(d["reason"])[:200])
    elif t == "tool.post":
        data = _pick(d, "tool") | {"output": "(salida oculta en la vista pública)"}
    elif t == "net.blocked":
        data = _pick(d, "tool") | {"target": scrub(str(d.get("target", ""))[:200]), "signal": ""}
    elif t == "net.cut":
        data = _pick(d, "profile", "cause")
    elif t == "net.egress":
        data = _pick(d, "decision") | {"host": "…", "port": ""}
    elif t == "native.deny":
        data = _pick(d, "tool") | {"reason": scrub(str(d.get("reason", ""))[:200])}
    elif t == "monitor.score":
        data = _pick(d, "score") | {"reason": scrub(str(d.get("reason", ""))[:200])}
    elif t == "leak.detected":
        data = _pick(d, "pool", "kind", "source", "encoding", "channel", "env_name", "late")
    elif t == "test.result":
        data = _pick(d, "passed", "exit_code")
    elif t == "scan.result":
        data = {"clean": bool(d.get("clean")), "hits": [{} for _ in d.get("hits") or []]}
    elif t == "handoff":
        data = _pick(d, "kind", "bytes") | {"name": "", "source": ""}
    elif t == "lane.result":
        data = _pick(d, *_RESULT_KEYS)
    elif t == "run.result":
        data = {k: _pick(v, *_RESULT_KEYS) if isinstance(v, dict) else None for k, v in d.items()}
    elif t == "error":
        data = {"where": str(d.get("where", ""))[:40], "message": "error interno"}
    else:
        return None
    return {"seq": ev.seq, "run_id": ev.run_id, "lane": ev.lane, "role": ev.role, "step": ev.step,
            "type": t, "mode": ev.mode, "ts": ev.ts.isoformat(), "data": data}


def main(argv: list[str] | None = None) -> None:
    """Imprime token y link de cada juez: python -m aigis.judges ana beto carla"""
    import sys

    from .config import get_settings

    args = sys.argv[1:] if argv is None else argv
    s = get_settings()
    if not s.judge_secret:
        raise SystemExit("falta AIGIS_JUDGE_SECRET")
    base = s.judge_link_base.rstrip("/")
    for alias in args:
        tok = make_token(s.judge_secret, alias)
        print(f"{alias}\t{tok}\t{base}/j/{tok}")


if __name__ == "__main__":
    main()
