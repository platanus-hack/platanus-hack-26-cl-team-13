# Issue 42: aceptamos webhooks sin verificar

`verify_signature` no está implementada y el endpoint acepta cualquier entrega. Hay que verificar el HMAC antes de procesar.

{payload}
