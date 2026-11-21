# blog-ia

Blog que genera resúmenes con la API de Claude. La llave se lee de `.env`.

## Convenciones

- `app.slug.slugify(title)` pasa a minúsculas, quita tildes (`ñ` queda `n`) y une palabras con `-`.
- Todo lo que no sea letra o dígito ASCII separa palabras. Sin guiones al inicio, al final ni repetidos.
- Máximo 60 caracteres, sin cortar una palabra: si la siguiente no cabe, se omite.
