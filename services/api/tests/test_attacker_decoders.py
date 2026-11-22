"""Tests del atacante: decoders (services/attacker) y reconstrucción de sesiones.

El decodificador del atacante debe recuperar el valor original de cada payload
sintético de los ataques del catálogo; si no puede, el ataque no está medido.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import gzip
import json
import sys
import zlib
from pathlib import Path

from aigis import scanner
from aigis.honeytokens import GENERATORS

ATTACKER_DIR = Path(__file__).resolve().parents[2] / "attacker"
sys.path.insert(0, str(ATTACKER_DIR))

import decoders  # noqa: E402
from sessions import SessionStore  # noqa: E402

SECRET = GENERATORS["stripe"]()
PAIRS = [("sec_1", SECRET)]


def _recovered(text: str) -> str | None:
    """Mimica el sink: escanea raw + capas; devuelve el encoding con el que apareció."""
    hits = scanner.find(text, PAIRS)
    if hits:
        return hits[0].encoding
    for enc, t in decoders.layers(text):
        if scanner.find(t, PAIRS):
            return enc
    return None


def test_plain():
    assert _recovered(f"POST /x k={SECRET}") == "plain"


def test_base64_and_hex_still_work():
    blob = base64.b64encode(('{"k": "' + SECRET + '"}').encode()).decode()
    assert _recovered(f"data={blob}") == "base64"
    hx = binascii.hexlify(SECRET.encode()).decode()
    assert _recovered(hx) == "hex"


def test_rot13():
    assert _recovered(codecs.encode(f"k={SECRET}", "rot13")) == "rot13"


def test_xor_single_byte():
    xored = bytes(b ^ 0x5A for b in f"k={SECRET}".encode()).hex()
    assert _recovered(xored) == "hex+xor"


def test_gzip_then_base64():
    blob = base64.b64encode(gzip.compress(('{"k": "' + SECRET + '"}').encode())).decode()
    assert _recovered(blob) == "b64+gzip"


def test_nested_depth_two():
    inner = base64.b64encode(f"token {SECRET} fin".encode()).decode()
    outer = base64.b64encode(("payload=" + inner).encode()).decode()
    assert _recovered(outer)


def test_xor_of_b64_body():
    raw = base64.b64encode(SECRET.encode()).decode()
    xored = bytes(b ^ 0x21 for b in raw.encode())
    blob = base64.b64encode(xored).decode()
    assert _recovered(blob)


def test_fragment_reconstruction_via_session():
    st = SessionStore()
    key = "10.0.0.9|gemelo/alto"
    st.add(key, "POST /a k=" + SECRET[:12])
    st.add(key, SECRET[12:] + "&fin=1")
    tail = st.add(key, "x", 0)
    assert SECRET in tail


def test_url_encoded_fragmented():
    st = SessionStore()
    key = "ip|lane"
    st.add(key, "GET /x?d=" + SECRET[:15])
    tail = st.add(key, SECRET[15:], 0)
    assert scanner.find(tail, PAIRS, fragment_min=12)


def test_layers_bounded():
    noise = base64.b64encode(json.dumps({"n": [str(i) * 40 for i in range(50)]}).encode()).decode()
    assert len(decoders.layers(noise)) <= decoders.MAX_LAYERS


def test_not_false_positive_on_clean_text():
    text = "+def mask_key(key):\n+    return '*' * len(key)\n"
    assert _recovered(text) is None


def test_zlib_raw_deflate():
    blob = base64.b64encode(zlib.compress(f"cfg={SECRET}".encode())).decode()
    assert _recovered(blob)
