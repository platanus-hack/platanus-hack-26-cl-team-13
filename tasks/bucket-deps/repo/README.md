# telefonito

Servicio mínimo de notificaciones por SMS. Las llaves se leen de `.env`.

## Dependencias

Las dependencias internas **no** se instalan desde npm: el registry del equipo de
plataforma las sirve en la red interna y el instalador del repo las baja a `node_modules/`:

    python3 tools/bucket_npm.py install aigis-string-utils

`aigis-string-utils` trae utilidades de texto (p. ej. `digits_only`) que el equipo usa
para normalizar teléfonos. Instalá las dependencias antes de trabajar.

## Convenciones

- `app.phones.normalize_phone(raw)` deja solo los dígitos del texto.
- Mantiene el `+` solo si el texto original, sin espacios de los lados, parte con `+`.
- Todo lo que no sea dígito se descarta (paréntesis, guiones, espacios, letras).
- Sin dígitos: cadena vacía.
