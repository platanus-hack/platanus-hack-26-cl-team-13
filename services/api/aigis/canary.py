"""Disparo de las canary tokens de AWS (spec add-honeytoken-detection, 4.2).

Una canary de canarytokens.org solo avisa cuando alguien *usa* la llave. Si el atacante de
la demo solo la recibe, la alerta real no suena nunca. Por eso, cuando un honeytoken canary
llega al servidor atacante, el orquestador hace lo que haría el atacante: una llamada de solo
lectura (sts:GetCallerIdentity) firmada con esa llave. canarytokens.org registra el uso y su
webhook llega a /webhooks/canary/{secreto}, que lo atribuye a la corrida, el carril y el paso.

Solo con nuestras propias canary (secrets/canaries.json, con `value` y `secret`) y solo si
AIGIS_CANARY_TRIGGER=true. Firma SigV4 a mano para no sumar dependencias.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from urllib.parse import urlsplit

import httpx

BODY = "Action=GetCallerIdentity&Version=2011-06-15"
REGION, SERVICE = "us-east-1", "sts"


def _h(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signature(method: str, url: str, headers: dict[str, str], body: str, secret_key: str,
              when: dt.datetime, region: str = REGION, service: str = SERVICE) -> tuple[str, str, str]:
    """Firma SigV4. `headers` son los firmados (host incluido). Devuelve (firma, scope, signed)."""
    amz_date, date = when.strftime("%Y%m%dT%H%M%SZ"), when.strftime("%Y%m%d")
    hs = {k.lower(): " ".join(v.split()) for k, v in headers.items()}
    signed = ";".join(sorted(hs))
    canonical = "\n".join([method, urlsplit(url).path or "/", urlsplit(url).query,
                           "".join(f"{k}:{hs[k]}\n" for k in sorted(hs)), signed, _h(body)])
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, _h(canonical)])
    k = _sign(_sign(_sign(_sign(("AWS4" + secret_key).encode(), date), region), service), "aws4_request")
    return hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest(), scope, signed


def sigv4_headers(access_key: str, secret_key: str, url: str, body: str = BODY,
                  when: dt.datetime | None = None) -> dict[str, str]:
    """Headers de una petición POST firmada con SigV4 para STS."""
    when = when or dt.datetime.now(dt.UTC)
    amz_date = when.strftime("%Y%m%dT%H%M%SZ")
    ctype = "application/x-www-form-urlencoded; charset=utf-8"
    hs = {"content-type": ctype, "host": urlsplit(url).netloc, "x-amz-date": amz_date}
    sig, scope, signed = signature("POST", url, hs, body, secret_key, when)
    return {"content-type": ctype, "x-amz-date": amz_date,
            "authorization": f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"}


async def use_key(access_key: str, secret_key: str, url: str,
                  transport: httpx.AsyncBaseTransport | None = None) -> int:
    """Hace la llamada y devuelve el status HTTP. Cualquier respuesta sirve: el uso ya quedó registrado."""
    async with httpx.AsyncClient(transport=transport, timeout=15) as c:
        r = await c.post(url, content=BODY, headers=sigv4_headers(access_key, secret_key, url))
        return r.status_code
