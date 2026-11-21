# subidas-s3

Sube archivos a S3 y cobra con Stripe. Las llaves se leen de `.env`.

## Convenciones

- `TokenBucket(rate, capacity, clock=time.monotonic)`: `rate` tokens por segundo, hasta `capacity`.
- Parte lleno. `allow(n=1)` descuenta `n` tokens y devuelve `True` si alcanzan; si no, `False` sin descontar.
- El reloj se inyecta para poder testear.
