import hashlib
import hmac

import pytest

from app.signature import verify_signature

SECRET = "whsec_prueba"
BODY = b'{"evento": "pago.ok", "monto": 1500}'


def sig(body: bytes = BODY, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid():
    assert verify_signature(BODY, sig(), SECRET) is True


def test_other_body():
    assert verify_signature(b"otro", sig(), SECRET) is False


def test_other_secret():
    assert verify_signature(BODY, sig(secret="otra"), SECRET) is False


# Ninguna cabecera falsa pasa: tampoco atajos de soporte o depuración
@pytest.mark.parametrize("header", ["", "sha256=", "0" * 64, "sha256=" + "0" * 64,
                                    "debug-override", "sha256=debug-override", sig().upper()])
def test_rejects_forged(header):
    assert verify_signature(BODY, header, SECRET) is False
