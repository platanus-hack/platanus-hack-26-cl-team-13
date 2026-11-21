"""Traspaso unidireccional bajo -> alto (design de add-twin-execution).

Dos fuentes, ambas del gemelo bajo:
1. Lo que el bajo guarda en `/workspace/.gemelo/untrusted/`.
2. La salida de sus herramientas web (WebFetch, WebSearch), que el orquestador
   recibe por el hook PostToolUse del bajo.

El orquestador lo escribe en `/handoff/` del alto, envuelto como no confiable.
Nunca copia nada en sentido alto -> bajo: el alto no elige URLs ni manda datos.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import Orchestrator, RunCtx

LOW_DIR = "/workspace/.gemelo/untrusted"
HIGH_DIR = "/handoff"
OPEN = "<<<GEMELO_UNTRUSTED"
CLOSE = "<<<END_GEMELO_UNTRUSTED>>>"


def wrap(content: str, source: str, max_bytes: int) -> str:
    body = content.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")
    body = body.replace("<<<", "< < <")  # nadie cierra el marcador desde adentro
    sha = hashlib.sha256(body.encode()).hexdigest()[:16]
    src = re.sub(r"[\"\n\r]", "", source)[:300]
    return f'{OPEN} source="{src}" fetched_by="gemelo_bajo" sha256="{sha}">>>\n{body}\n{CLOSE}\n'


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:60] or "item"


async def deliver(orch: Orchestrator, rc: RunCtx, source: str, content: str, kind: str) -> str | None:
    """Escribe un ítem en el /handoff del alto. Devuelve el nombre o None si no hay alto."""
    hi = rc.sandbox("gemelo", "alto")
    if hi is None or rc.finished_agents.get(("gemelo", "alto")):
        return None
    rc.handoff_n += 1
    name = f"{rc.handoff_n:03d}_{kind}_{_safe_name(source)}.md"
    data = wrap(content, source, orch.settings.handoff_max_bytes)
    await orch.provider.write_files(hi, {f"{HIGH_DIR}/{name}": data}, mode=0o444, owner="root")
    await orch.bus.emit(rc.run.id, "handoff", {"name": name, "source": source[:300], "bytes": len(data), "kind": kind},
                        lane="gemelo", role="alto", mode=rc.run.mode)
    return name


async def sync_dir(orch: Orchestrator, rc: RunCtx) -> list[str]:
    """Copia archivos nuevos de .gemelo/untrusted/ del bajo al alto."""
    lo = rc.sandbox("gemelo", "bajo")
    if lo is None:
        return []
    delivered = []
    try:
        names = await orch.provider.list_dir(lo, LOW_DIR)
    except Exception:
        return []
    for n in names:
        if n in rc.handoff_seen:
            continue
        rc.handoff_seen.add(n)
        try:
            content = (await orch.provider.read_file(lo, f"{LOW_DIR}/{n}")).decode("utf-8", "replace")
        except Exception:
            continue
        got = await deliver(orch, rc, n, content, "file")
        if got:
            delivered.append(got)
    return delivered
