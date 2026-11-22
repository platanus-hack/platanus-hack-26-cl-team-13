# pagos-webhooks

Recibe webhooks del proveedor de pagos. La configuración se lee de `.env` con `app/config.py`.

## Convenciones

- `app.signature.verify_signature(payload, header, secret)` devuelve `True` solo si `header`
  es `sha256=` seguido del HMAC-SHA256 en hex de `payload` (bytes) con `secret`.
- La comparación es en tiempo constante.
- Cualquier otra cabecera (vacía, sin prefijo, con otro hex) devuelve `False`.
