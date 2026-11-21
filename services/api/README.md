# Orquestador de Gemelo (`services/api`)

Recibe un ataque y una tarea, y los corre en cuatro carriles con cinco cajas: sin defensa, monitor, FIDES y Gemelo (bajo y alto). Entrega el diff del gemelo alto si pasan los tests y el escáner de secretos. Spec completo en `docs/spec-orquestador.md`.

## Correr

```bash
cd services/api
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"   # en Linux: .venv/bin/python
.venv/Scripts/python -m pytest -q                 # provider falso, sin Docker ni API
make -C ../.. sandbox-image                        # imágenes gemelo-sandbox y gemelo-proxy
.venv/Scripts/python -m pytest -q -m docker        # conformidad del provider Docker
GEMELO_SANDBOX_PROVIDER=local GEMELO_AGENT=scripted .venv/Scripts/python -m uvicorn gemelo.app:app --port 8000
```

Variables con prefijo `GEMELO_`, ver `gemelo/config.py`. `GEMELO_AGENT=claude` usa Claude Code real a través del gateway (`GEMELO_GATEWAY_URL`, `GEMELO_GATEWAY_STUB=false`).

## API

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/tasks` | tareas disponibles |
| `POST` | `/runs` | `{"task_id", "attack": {"vector": "readme"|"issue"|"webpage", "payload"}}` |
| `GET` | `/runs/{id}` | estado y resultado por carril |
| `GET` | `/runs/{id}/events?after=N` | SSE, reanudable con `Last-Event-ID` |
| `GET` | `/runs/{id}/lanes/{lane}/diff` | diff; en gemelo solo si se entregó |
| `POST` | `/runs/{id}/cancel` | cancela y limpia |
| `GET` | `/queue` | cola visible |

Desde las cajas: `/hooks/{run}/{lane}/{role}/{pre,post}` y `/internal/egress` (proxy). Webhooks: `/webhooks/attacker` (HMAC `X-Gemelo-Signature`) y `/webhooks/canary/{secreto}`.

## Módulos

| Archivo | Qué hace |
|---|---|
| `runner.py` | cola, ciclo de una corrida, preparación de cajas, hooks, consolidación |
| `lanes/` | defensa de cada carril en los hooks |
| `providers/` | interfaz `SandboxProvider`; `local` (Docker), `fake` (tests), `e2b` (pendiente) |
| `accept.py` | diff, tests sin red y escaneo del diff |
| `scanner.py` | secretos en claro, base64 (3 alineaciones), hex, url, fragmentos |
| `honeytokens.py` | pools A (honeytokens) y B (sintéticos), únicos por caja |
| `handoff.py` | traspaso bajo -> alto, marcado no confiable |
| `leaks.py` | atribución de filtraciones a corrida, carril, gemelo y paso |
| `gateway_client.py` | contrato con el gateway de P2 y stub |
| `gateway/` | gateway del modelo (servicio aparte), ver la sección Gateway |
| `store.py` | interfaz `Store`; `MemoryStore` (P3 agrega Postgres) |

## Gateway del modelo

Servicio aparte (`uvicorn gemelo.gateway.app:app`, imagen `Dockerfile.gateway`). Es el único proceso que conoce la API key de Anthropic. Las cajas reciben `ANTHROPIC_BASE_URL=<url pública del gateway>`, `ANTHROPIC_AUTH_TOKEN=<token gw_>` y, si el token es por corrida, `ANTHROPIC_CUSTOM_HEADERS="X-Gemelo-Lane: <lane>/<role>"`.

### Variables (prefijo `GATEWAY_`)

| Variable | Por defecto | Uso |
|---|---|---|
| `GATEWAY_UPSTREAM_URL` | `https://api.anthropic.com` | base del upstream. Con el proxy de la hackatón: `https://llm.hack.platan.us/t/<phk_token>/anthropic` (secreto) |
| `GATEWAY_UPSTREAM_API_KEY` | vacío | key de Anthropic; el proxy de la hackatón también la exige |
| `GATEWAY_ADMIN_TOKEN` | vacío | Bearer del orquestador para `/admin`; vacío deshabilita `/admin` |
| `GATEWAY_MODEL` | `claude-haiku-5-5` | modelo fijado para todo pedido |
| `GATEWAY_ALLOWED_MODELS` | vacío | modelos que se respetan si el agente los pide (separados por coma) |
| `GATEWAY_DEFAULT_BUDGET_USD` / `GATEWAY_MAX_BUDGET_USD` | `2.5` / `20` | tope por token por defecto y máximo emitible |
| `GATEWAY_DEFAULT_TTL_S` / `GATEWAY_MAX_TTL_S` | `1800` / `14400` | vida del token |
| `GATEWAY_MAX_REQUESTS` | `400` | llamadas al modelo por token (0 = sin tope) |
| `GATEWAY_PRICES_JSON` | vacío | corrige precios por MTok: `{"modelo": [in, out, cache_write, cache_read]}` |

### Rutas de administración (`Authorization: Bearer $GATEWAY_ADMIN_TOKEN`)

| Método | Request | Response |
|---|---|---|
| `POST /admin/tokens` | `{run_id, budget_usd?, ttl_s?, lane?, role?}` | `{token, expires_at, budget_usd}` |
| `DELETE /admin/tokens/{token}` | | `204`, idempotente |
| `GET /admin/tokens/{token}/usage` | | `{run_id, state, budget_usd, remaining_usd, cost_usd, input_tokens, output_tokens, cache_*, requests, cut, by_lane}` |
| `DELETE /admin/runs/{run_id}` | | `{revoked: n}`: revoca todos los tokens de la corrida |
| `GET /admin/runs/{run_id}/usage` | | `{cost_usd, requests, tokens, by_lane}` sumado sobre los tokens de la corrida |

Con `lane` (y `role`) en la emisión, el uso se atribuye a ese carril y `X-Gemelo-Lane` se ignora. Sin ellos, el carril sale del header (`<lane>/<role>`, solo `[a-z0-9_-]`; otro valor cuenta como `unknown`). El header falsificado solo mueve la atribución dentro del mismo token, nunca el tope.

### Rutas del agente

- `POST /v1/messages` (también `?beta=true`), con o sin `stream`. Token en `Authorization: Bearer` o `x-api-key`.
- `POST /v1/messages/count_tokens`, sin costo.
- Cualquier otra ruta responde `404`.

Errores, en el formato de Anthropic y con `x-should-retry: false`:

| Status | `error.type` | Cuándo |
|---|---|---|
| `401` | `authentication_error` | token ausente, desconocido, revocado o expirado |
| `402` | `billing_error` | el saldo del token no alcanza para `min_output_tokens` de salida; `usage.cut = "budget"` |
| `403` | `permission_error` | se pasó `GATEWAY_MAX_REQUESTS`; `usage.cut = "requests"` |
| `502` | `api_error` | upstream inalcanzable o rechazó la key del gateway |

Otros errores del upstream (429, 529, 400) se reenvían tal cual y no se cobran.

### Cómo se cumple el tope

Antes de reenviar, el gateway reserva el peor caso de la llamada: entrada estimada en 3 bytes por token más 1.000 de margen, cobrada a la tarifa más cara (escritura de caché a 1 h), más `max_tokens` de salida. `max_tokens` se recorta para que esa reserva quepa en el saldo. Al terminar, la reserva se cambia por el costo real del `usage`. Un stream cortado antes de `message_stop` se cobra por la reserva completa, porque el upstream pudo seguir generando. Con eso el gasto de un token no supera su tope aunque haya llamadas en paralelo.

Los precios están en `gemelo/gateway/pricing.py`, marcados por verificar contra la página oficial de precios.

### Seguridad

- Se guarda el sha256 de cada token, no el token.
- La key y la URL del upstream solo se leen del entorno; ninguna respuesta, log ni header las contiene (test `test_la_key_no_sale_en_respuestas`).
- Al upstream solo pasan `anthropic-version`, `anthropic-beta`, `content-type` y `accept`; `Authorization`, `x-api-key` del agente y `X-Gemelo-Lane` se descartan.
- El contenedor corre uvicorn sin access log, porque las rutas `/admin/tokens/{token}` llevan el token.
- Estado en memoria: reiniciar el servicio invalida los tokens vivos.

### Render

Servicio web propio con esta entrada en `render.yaml`:

```yaml
  - type: web
    name: gemelo-gateway
    runtime: docker
    plan: starter            # el plan gratis duerme y se pierden los tokens en memoria
    dockerfilePath: ./services/api/Dockerfile.gateway
    dockerContext: .
    healthCheckPath: /health
    autoDeploy: true
    envVars:
      - key: GATEWAY_UPSTREAM_URL
        sync: false          # https://llm.hack.platan.us/t/<phk_token>/anthropic
      - key: GATEWAY_UPSTREAM_API_KEY
        sync: false
      - key: GATEWAY_ADMIN_TOKEN
        sync: false          # el mismo valor que GEMELO_GATEWAY_ADMIN_TOKEN del orquestador
      - key: GATEWAY_MODEL
        value: claude-haiku-5-5
```

En el orquestador: `GEMELO_GATEWAY_STUB=false`, `GEMELO_GATEWAY_URL` y `GEMELO_GATEWAY_URL_SANDBOX` con la URL pública HTTPS del gateway (host exacto, puerto 443, para que el filtro de E2B lo permita).
