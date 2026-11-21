"""Búsqueda de secretos conocidos en texto, con sus codificaciones (decisión D3).

Lo usan el escaneo del diff del gemelo alto, FIDES (salida de herramientas),
la atribución de lo que llega al atacante y el redactor de eventos.

Cubre: claro, base64 estándar y url-safe (con y sin padding, tres alineaciones),
hex en minúsculas y mayúsculas, url-encoding y fragmentos en claro.
Lo demás (rot13, XOR, cifrado) es un límite declarado.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote


@dataclass(frozen=True)
class Hit:
    secret_id: str
    encoding: str
    offset: int


def _b64_cores(value: bytes, alphabet: str) -> list[str]:
    enc = base64.b64encode if alphabet == "std" else base64.urlsafe_b64encode
    out = []
    n = len(value)
    for k in range(3):
        full = enc(b"\0" * k + value).decode().rstrip("=")
        skip = (0, 2, 3)[k]
        end = ((k + n) // 3) * 4
        core = full[skip:end]
        if len(core) >= 8:
            out.append(core)
    padded = enc(value).decode()
    out.append(padded)
    return out


@lru_cache(maxsize=4096)
def variants(value: str) -> tuple[tuple[str, str], ...]:
    """Devuelve (codificación, forma) para un valor. El orden importa: claro primero."""
    raw = value.encode()
    forms: list[tuple[str, str]] = [("plain", value)]
    for alpha in ("std", "url"):
        for core in _b64_cores(raw, alpha):
            forms.append(("base64", core))
    hx = binascii.hexlify(raw).decode()
    forms += [("hex", hx), ("hex", hx.upper())]
    q = quote(value, safe="")
    if q != value:
        forms.append(("url", q))
    seen: set[str] = set()
    uniq = []
    for enc, f in forms:
        if f not in seen:
            seen.add(f)
            uniq.append((enc, f))
    return tuple(uniq)


def find(text: str, secrets: Iterable[tuple[str, str]], fragment_min: int | None = None) -> list[Hit]:
    """Busca cada (secret_id, valor) en `text`.

    `fragment_min`: si se da, también reporta subcadenas en claro del valor de ese
    largo o más (para fragmentos). Se usa con 16 en el diff y 8 en el atacante.
    """
    hits: list[Hit] = []
    if not text:
        return hits
    for sid, value in secrets:
        if not value:
            continue
        found = False
        for enc, form in variants(value):
            idx = text.find(form)
            if idx >= 0:
                hits.append(Hit(sid, enc, idx))
                found = True
                break
        if found or not fragment_min or len(value) <= fragment_min:
            continue
        for i in range(0, len(value) - fragment_min + 1):
            frag = value[i : i + fragment_min]
            idx = text.find(frag)
            if idx >= 0:
                hits.append(Hit(sid, "fragment", idx))
                break
    return hits


_B64_BLOB = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX_BLOB = re.compile(r"\b(?:[0-9a-fA-F]{2}){8,}\b")


def decode_layers(text: str, depth: int = 2) -> list[str]:
    """Decodifica blobs base64 y hex anidados, para cubrir envoltorios (JSON en base64)."""
    out: list[str] = []
    frontier = [text]
    for _ in range(depth):
        nxt: list[str] = []
        for t in frontier:
            for m in _B64_BLOB.findall(t):
                for dec in (base64.b64decode, base64.urlsafe_b64decode):
                    try:
                        s = dec(m + "=" * (-len(m) % 4)).decode("utf-8")
                    except Exception:
                        continue
                    if s.isprintable() or "\n" in s:
                        nxt.append(s)
                        break
            for m in _HEX_BLOB.findall(t):
                try:
                    nxt.append(bytes.fromhex(m).decode("utf-8"))
                except Exception:
                    pass
        out += nxt
        frontier = nxt
    return out


def redact(text: str, secrets: Iterable[tuple[str, str]]) -> str:
    """Reemplaza cada forma conocida de cada secreto por [[secret_id]]."""
    pairs = []
    for sid, value in secrets:
        if value:
            for _, form in variants(value):
                pairs.append((form, sid))
    # Formas largas primero para no dejar restos
    for form, sid in sorted(pairs, key=lambda p: -len(p[0])):
        if form in text:
            text = text.replace(form, f"[[{sid}]]")
    return text
