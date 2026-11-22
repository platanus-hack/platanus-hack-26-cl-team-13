# Orquestador de AIgis (`services/api`)

Recibe un ataque y una tarea, y los corre en cuatro carriles con cinco cajas: sin defensa, monitor, FIDES y Gemelo (alto y bajo). Entrega el diff del gemelo bajo si pasan los tests y el escáner de secretos. Spec completo en `docs/spec-orquestador.md`.

## Correr

Un solo juego de comandos para Windows, macOS y Linux, con [uv](https://docs.astral.sh/uv) (instala Python 3.12 y las dependencias del `uv.lock`):

```bash
cd services/api
uv sync                                   # una vez, o cuando cambie uv.lock
uv run uvicorn aigis.app:app --host 0.0.0.0 --port 8000   # 0.0.0.0: las cajas Docker la alcanzan por host.docker.internal
uv run pytest                             # tests con provider falso, sin Docker ni API
```

Desde la raíz del repo es lo mismo con `make api` y `make test`.

Por defecto la API usa el provider Docker local (`AIGIS_SANDBOX_PROVIDER=local`) y el agente con guion (`AIGIS_AGENT=scripted`). Opciones:

| Para | Variable o comando |
|---|---|
| Probar sin Docker | `AIGIS_SANDBOX_PROVIDER=fake` (no aísla nada) |
| Cajas en E2B | `AIGIS_SANDBOX_PROVIDER=e2b`, `E2B_API_KEY` y `AIGIS_PUBLIC_BASE_URL` |
| Claude Code real | `AIGIS_AGENT=claude`, `AIGIS_GATEWAY_STUB=false` y la URL del gateway |
| Pedir token en la API | `AIGIS_API_TOKEN` (en Render siempre) |
| Corte global de presupuesto | `AIGIS_BUDGET_USD` (crédito live; 0 = sin corte) y `AIGIS_BUDGET_CUT_RATIO` (0.9) |
| Disparar la alerta real de las canary | `AIGIS_CANARY_TRIGGER=true` y canaries con `secret` en `secrets/canaries.json` (sale a AWS STS) |
| Llaves partidas en varias peticiones | `AIGIS_FRAGMENT_COVERAGE` (0.9), `AIGIS_FRAGMENT_MIN_LEN` (4), `AIGIS_FRAGMENT_WINDOW_S` (900), `AIGIS_FRAGMENT_TOKEN_MAX` (256) |
| Guardar en Postgres | `DATABASE_URL` |
| Conformidad Docker | `make sandbox-image` y `uv run pytest -m docker` |
| Conformidad E2B | `uv run python -m aigis.providers.e2b_template` y `uv run pytest -m e2b` |

Las variables pueden ir en `.env` (ignorado por git). Todas llevan prefijo `AIGIS_` salvo `DATABASE_URL` y `E2B_API_KEY`; ver `gemelo/config.py`.

## API

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/health` | estado; único endpoint sin token |
| `GET` | `/tasks` | tareas disponibles |
| `POST` | `/runs` | `{"task_id", "attack": {"vector": "readme"|"issue"|"webpage", "payload"}}`; opcional `"ablate": ["honeytokens"|"diff_scan"|"handoff"|"allowlist"|"low_hints"]` (exige el carril gemelo) |
| `GET` | `/runs/{id}` | estado y resultado por carril |
| `GET` | `/runs/{id}/events?after=N` | SSE, reanudable con `Last-Event-ID` |
| `GET` | `/runs/{id}/lanes/{lane}/diff` | diff; en gemelo solo si se entregó |
| `POST` | `/runs/{id}/cancel` | cancela y limpia |
| `GET` | `/runs/{id}/chain` | cadena del ataque por carril y caja: no confiable → secreto → codificación → salida → desenlace |
| `GET` | `/runs/{id}/usage` | uso real del gateway; `by_lane` con claves `<carril>/<rol>` y `<carril>/monitor` |
| `GET` | `/budget` | gasto real (`aigis_usage`) + reserva de `AIGIS_RUN_BUDGET_USD` por corrida sin terminar, contra el corte |
| `GET` | `/queue` | cola visible |

Con `AIGIS_BUDGET_USD` > 0, `POST /runs` responde **429 `{"error": "budget", "detail", "retry_after_s"}`** (el mismo contrato que la API de jueces) cuando la corrida nueva llevaría lo comprometido sobre `AIGIS_BUDGET_CUT_RATIO × AIGIS_BUDGET_USD`. La web cae entonces a las grabaciones.

Con `AIGIS_API_TOKEN` definido, todas las rutas de esta tabla salvo `/health` piden `Authorization: Bearer <token>`. El panel web lo agrega en su proxy.

Desde las cajas: `/hooks/{run}/{lane}/{role}/{pre,post}` y `/internal/egress` (proxy). Webhooks: `/webhooks/attacker` (HMAC `X-Aigis-Signature`) y `/webhooks/canary/{secreto}`.

## Módulos

| Archivo | Qué hace |
|---|---|
| `runner.py` | cola, ciclo de una corrida, preparación de cajas, hooks, consolidación |
| `lanes/` | defensa de cada carril en los hooks |
| `providers/` | interfaz `SandboxProvider`; `local` (Docker), `e2b` y `fake` (tests) |
| `accept.py` | diff, tests sin red y escaneo del diff |
| `scanner.py` | secretos en claro, base64 (3 alineaciones), hex, url, fragmentos |
| `honeytokens.py` | pools A (honeytokens) y B (sintéticos), únicos por caja |
| `handoff.py` | traspaso alto -> bajo, marcado no confiable |
| `leaks.py` | atribución de filtraciones a corrida, carril, gemelo y paso; llaves partidas en varias peticiones |
| `canary.py` | usa una canary recibida por el atacante (STS firmado con SigV4) para que suene la alerta real |
| `divergence.py` | compara los dos gemelos paso a paso; fuga contrafactual del bajo |
| `chain.py` | cadena del ataque desde los eventos guardados |
| `gateway_client.py` | contrato con el gateway de P2 y stub |
| `gateway/` | gateway del modelo (servicio aparte), ver la sección Gateway |
| `store.py`, `store_pg.py` | interfaz `Store`; `MemoryStore` y `PostgresStore` (con `DATABASE_URL`) |

## Gateway del modelo

Servicio aparte (`uvicorn aigis.gateway.app:app`, imagen `Dockerfile.gateway`). Es el único proceso que conoce la API key de Anthropic. Las cajas reciben `ANTHROPIC_BASE_URL=<url pública del gateway>`, `ANTHROPIC_AUTH_TOKEN=<token gw_>` y, si el token es por corrida, `ANTHROPIC_CUSTOM_HEADERS="X-Aigis-Lane: <lane>/<role>"`.

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

Con `lane` (y `role`) en la emisión, el uso se atribuye a ese carril y `X-Aigis-Lane` se ignora. Sin ellos, el carril sale del header (`<lane>/<role>`, solo `[a-z0-9_-]`; otro valor cuenta como `unknown`). El header falsificado solo mueve la atribución dentro del mismo token, nunca el tope.

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
- Al upstream solo pasan `anthropic-version`, `anthropic-beta`, `content-type` y `accept`; `Authorization`, `x-api-key` del agente y `X-Aigis-Lane` se descartan.
- El contenedor corre uvicorn sin access log, porque las rutas `/admin/tokens/{token}` llevan el token.
- Estado en memoria: reiniciar el servicio invalida los tokens vivos.

### Render

Servicio web propio con esta entrada en `render.yaml`:

```yaml
  - type: web
    name: aigis-gateway
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
        sync: false          # el mismo valor que AIGIS_GATEWAY_ADMIN_TOKEN del orquestador
      - key: GATEWAY_MODEL
        value: claude-haiku-5-5
```

En el orquestador: `AIGIS_GATEWAY_STUB=false`, `AIGIS_GATEWAY_URL` y `AIGIS_GATEWAY_URL_SANDBOX` con la URL pública HTTPS del gateway (host exacto, puerto 443, para que el filtro de E2B lo permita).
