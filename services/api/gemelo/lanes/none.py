"""Carril sin defensa (baseline): red abierta, secretos del pool B, hooks solo registran."""

from __future__ import annotations

from . import Defense


class NoDefense(Defense):
    hook_fail = "open"
