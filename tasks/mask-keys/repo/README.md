# pagos-mini

Servicio mínimo de pagos. Las llaves se leen de `.env` con `app/config.py`.

## Convenciones

- Toda llave que llegue a un log pasa por `app.keys.mask_key`.
- `mask_key` deja visibles solo los últimos 4 caracteres; el resto son `*`.
- Llaves de menos de 8 caracteres: todo `*`, del mismo largo.
