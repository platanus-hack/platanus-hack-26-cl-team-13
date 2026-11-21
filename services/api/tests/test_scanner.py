import base64
import binascii
from urllib.parse import quote

import pytest

from gemelo import scanner
from gemelo.honeytokens import GENERATORS, SecretRegistry

SECRET = "sk_live_" + "Ab3dE6gH9jK2mN5pQ8sT1vW4"
PAIRS = [("sec_1", SECRET)]


@pytest.mark.parametrize("prefix", ["", "x", "xy", "hola mundo "])
def test_base64_any_alignment(prefix):
    blob = base64.b64encode((prefix + SECRET + " fin").encode()).decode()
    hits = scanner.find(f"data={blob}", PAIRS)
    assert hits and hits[0].encoding == "base64"


def test_plain_hex_url():
    assert scanner.find(f"x {SECRET} y", PAIRS)[0].encoding == "plain"
    hx = binascii.hexlify(SECRET.encode()).decode()
    assert scanner.find(hx, PAIRS)[0].encoding == "hex"
    assert scanner.find(hx.upper(), PAIRS)[0].encoding == "hex"
    weird = "a+b/c=" + SECRET
    assert scanner.find(quote(weird, safe=""), [("s", weird)])


def test_urlsafe_base64_without_padding():
    blob = base64.urlsafe_b64encode(SECRET.encode()).decode().rstrip("=")
    assert scanner.find(blob, PAIRS)


def test_fragment():
    assert not scanner.find(SECRET[3:20], PAIRS)
    assert scanner.find("..." + SECRET[3:20] + "...", PAIRS, fragment_min=16)[0].encoding == "fragment"


def test_clean_diff():
    assert scanner.find("+def mask_key(key):\n+    return '*' * len(key)\n", PAIRS, fragment_min=16) == []


def test_nested_layers():
    inner = base64.b64encode(('{"k": "' + SECRET + '"}').encode()).decode()
    outer = base64.b64encode(f"payload={inner}".encode()).decode()
    layers = scanner.decode_layers(outer)
    assert any(scanner.find(t, PAIRS) for t in layers)


def test_redact_removes_every_form():
    text = f"{SECRET} {base64.b64encode(SECRET.encode()).decode()} {binascii.hexlify(SECRET.encode()).decode()}"
    out = scanner.redact(text, PAIRS)
    assert SECRET not in out and "[[sec_1]]" in out
    assert not scanner.find(out, PAIRS)


def test_registry_unique_per_box_and_pools():
    reg = SecretRegistry()
    spec = [("STRIPE_API_KEY", "stripe"), ("AWS_ACCESS_KEY_ID", "aws_access_key")]
    lo = reg.assign("r1", "gemelo", "bajo", spec)
    hi = reg.assign("r1", "gemelo", "alto", spec)
    assert {s.pool for s in lo} == {"A"} and {s.pool for s in hi} == {"B"}
    assert not {s.value for s in lo} & {s.value for s in hi}
    assert hi[0].value.startswith("sk_live_") and hi[1].value.startswith("AKIA") and len(hi[1].value) == 20


def test_generators_have_real_shape():
    for kind, gen in GENERATORS.items():
        a, b = gen(), gen()
        assert a != b and len(a) >= 20, kind
