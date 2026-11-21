#!/usr/bin/env python3
"""Hook PreToolUse / PostToolUse del agente dentro del sandbox.

Claude Code lo llama así (ver sandbox/settings.json):
    python3 /opt/gemelo/hooks/hook.py pre    # PreToolUse
    python3 /opt/gemelo/hooks/hook.py post   # PostToolUse

Lee el JSON del hook por stdin y lo reenvía al orquestador:
    POST $GEMELO_HOOK_URL/{pre|post}   Authorization: Bearer $GEMELO_HOOK_TOKEN
El orquestador responde {"decision": "allow"|"deny", "reason": "..."}.

Si el orquestador no responde: GEMELO_HOOK_FAIL=closed niega, open deja pasar.
Solo biblioteca estándar. Usa el proxy del entorno (HTTP_PROXY) si está definido.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

TIMEOUT_S = 10


def call(phase: str, payload: dict) -> dict:
    url = os.environ.get("GEMELO_HOOK_URL", "").rstrip("/")
    fail = os.environ.get("GEMELO_HOOK_FAIL", "closed")
    fallback = {"decision": "allow" if fail == "open" else "deny", "reason": "orquestador sin respuesta"}
    if not url:
        return fallback
    req = urllib.request.Request(
        f"{url}/{phase}",
        data=json.dumps(payload, default=str).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ.get('GEMELO_HOOK_TOKEN', '')}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read() or b"{}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return fallback


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    resp = call(phase, payload)
    if phase == "pre" and resp.get("decision") == "deny":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": resp.get("reason") or "negado por Gemelo",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
