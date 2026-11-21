# inventario-api

API de inventario. La configuración se lee de `.env` con `app/config.py`.

## Convenciones

- `app.dsn.parse_dsn(url)` devuelve un dict con `scheme`, `user`, `password`, `host`, `port` y `database`.
- Los campos ausentes van como `None`; `port` es `int` y por defecto 5432 si el esquema es `postgres` o `postgresql`.
- Usuario y contraseña se decodifican (`%40` es `@`).
