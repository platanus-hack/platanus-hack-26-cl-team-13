"""Decodificadores del atacante: solo biblioteca estándar, sin dependencias.

Mismo criterio que aigis/scanner.py (claro, base64 std/url en 3 alineaciones, hex,
url-encode, fragmentos) y encima: rot13, XOR de 1 byte por fuerza bruta, gzip/zlib,
hex dentro de base64 y profundidad configurable (por defecto 4).

Devuelve capas etiquetadas (label, texto). El sink manda raw + capas al orquestador,
que empareja contra el registro de secretos; así el atacante aporta el "con qué
encoding apareció" sin saber nada de los carriles.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import gzip
import re
import string
import urllib.parse
import zlib

_B64_BLOB = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX_BLOB = re.compile(r"\b(?:[0-9a-fA-F]{2}){8,}\b")
_OK_CHARS = set(string.printable)
_ALNUM = set(string.ascii_letters + string.digits)
MAX_LAYERS = 256


def _clean(bs: bytes) -> str | None:
    try:
        s = bs.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not s or any(c not in _OK_CHARS for c in s):
        return None
    return s


def _b64_bytes(m: str) -> bytes | None:
    pad = m + "=" * (-len(m) % 4)
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return dec(pad)
        except (binascii.Error, ValueError):
            continue
    return None


def _inflate(bs: bytes) -> bytes | None:
    for wbits in (47, 15, -15):
        try:
            return zlib.decompress(bs, wbits)
        except zlib.error:
            continue
    try:
        return gzip.decompress(bs)
    except (gzip.BadGzipFile, zlib.error, EOFError):
        return None


def _xor1(bs: bytes, keep: int = 3) -> list[bytes]:
    """Fuerza bruta XOR de 1 byte. Devuelve los mejores candidatos por proporción alfanumérica
    (basura plausible compite con la clave correcta, así que no nos quedamos con el primero)."""
    out = []
    for k in range(1, 256):
        s = _clean(bytes(b ^ k for b in bs))
        if not s:
            continue
        ratio = sum(c in _ALNUM for c in s) / len(s)
        if ratio >= 0.6:
            out.append((ratio, k, bytes(b ^ k for b in bs)))
    out.sort(key=lambda x: -x[0])
    return [b for _, _, b in out[:keep]]


def layers(text: str, depth: int = 4) -> list[tuple[str, str]]:
    """Capas derivadas de `text` (sin incluir el original), deduplicadas y acotadas."""
    out: list[tuple[str, str]] = []
    seen: set[str] = {text}
    frontier: list[tuple[str, str]] = [("", text)]
    for _ in range(max(1, depth)):
        nxt: list[tuple[str, str]] = []
        for origin, t in frontier:
            candidates: list[tuple[str, str | bytes]] = []

            r13 = codecs.encode(t, "rot13")
            if r13 != t:
                candidates.append(("rot13", r13))
            if "%" in t:
                try:
                    q = urllib.parse.unquote(t)
                except Exception:  # noqa: BLE001
                    q = ""
                if q and q != t:
                    candidates.append(("url", q))

            for m in _B64_BLOB.findall(t):
                bs = _b64_bytes(m)
                if not bs:
                    continue
                candidates.append(("b64", bs))
                if inf := _inflate(bs):
                    candidates.append(("b64+gzip", inf))
                for x in _xor1(bs):
                    candidates.append(("b64+xor", x))
            for m in _HEX_BLOB.findall(t):
                try:
                    bs = binascii.unhexlify(m)
                except (binascii.Error, ValueError):
                    continue
                candidates.append(("hex", bs))
                if inf := _inflate(bs):
                    candidates.append(("hex+gzip", inf))
                for x in _xor1(bs):
                    candidates.append(("hex+xor", x))
            for x in _xor1(t.encode("utf-8", "replace")):
                candidates.append(("xor", x))

            for label, val in candidates:
                s = val.decode("utf-8", "replace") if isinstance(val, bytes) else val
                if not s or s in seen or s == t:
                    continue
                seen.add(s)
                lab = f"{origin}+{label}" if origin else label
                out.append((lab, s))
                nxt.append((lab, s))
                if len(out) >= MAX_LAYERS:
                    return out
        frontier = nxt
        if not frontier:
            break
    return out
