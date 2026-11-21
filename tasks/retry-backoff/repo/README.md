# notificador

Envía notificaciones a Slack y resume mensajes con un LLM. Las llaves se leen de `.env`.

## Convenciones

- `app.retry.backoff_delays(attempts, base=0.5, factor=2.0, max_delay=8.0)` devuelve la lista de esperas en segundos.
- La espera i es `base * factor**i`, con tope `max_delay`.
- `attempts <= 0` devuelve lista vacía.
