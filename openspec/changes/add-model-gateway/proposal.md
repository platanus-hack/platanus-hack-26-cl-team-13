# Proposal

## Why

Cada carril corre Claude Code real, y el modelo se paga con cuentas de ~50 USD. Si la API key de Anthropic entrara a un sandbox, cualquier agente atacado podría filtrarla; y sin un punto central no hay forma de grabar respuestas para desarrollar sin gastar, de cortar el gasto ni de reproducir la demo sin API. El gateway resuelve los tres problemas y es la segunda pieza del spike de F0 (Claude Code headless en E2B pasando por el gateway).

## What Changes

- Un servicio gateway que hace de proxy hacia `api.anthropic.com`; los sandboxes reciben `ANTHROPIC_BASE_URL` apuntando al gateway y nunca la key.
- Tokens por corrida (decisión D4): se emiten al crear la corrida, solo sirven para esa corrida, **expiran al terminarla** y tienen **su propio tope en USD**.
- Modos `live`, `record` y `replay` con `MODEL_MODE`. `record` guarda casetes en `cassettes/`; `replay` reproduce por orden de llamada, sin red hacia Anthropic.
- Cuentas por propósito (`ANTHROPIC_KEY_DEMO`, `_EVAL`, `_DEV_1..n`) con corte por presupuesto; si se corta la cuenta de producción, la demo pasa a replay.
- El modelo lo fija el gateway (por defecto `claude-haiku-5-5`), no el agente.
- Registro de cada llamada: corrida, carril, gemelo, tokens consumidos y costo.
- Contrato de eventos de corrida que consumen el orquestador, los carriles y la web.
- Fuera de alcance (F3): tope por persona, panel de gasto y cupo de corridas en vivo por hora.

## Capabilities

### New Capabilities
- `model-gateway`: acceso de los sandboxes al modelo a través de un proxy que guarda la key, autentica por corrida, controla el gasto y graba o reproduce respuestas.
- `run-events`: formato y entrega de los eventos de una corrida (pasos del agente, llamadas al modelo, red, detecciones) para los carriles y la web.

### Modified Capabilities
<!-- Ninguna: no hay specs existentes. -->

## Impact

- Código: `services/api/gemelo/gateway.py`, `services/api/gemelo/store.py` (registro de uso y tokens), `docker-compose.yml` (servicio gateway en ambas redes), `.env.example`.
- **Renombre de variables**: `.env.example` hoy tiene `ANTHROPIC_API_KEY` y `GATEWAY_MODE`; pasan a `ANTHROPIC_KEY_DEMO`/`_EVAL`/`_DEV_n` y `MODEL_MODE`, como en el plan.
- Dependencias: FastAPI, httpx, sse-starlette, SQLAlchemy, Postgres.
- Datos: `cassettes/` se commitea; no puede contener keys ni tokens.
- Lo consumen: `add-sandbox-provider` (destino permitido del perfil aislado), `add-twin-execution`, `add-baseline-lanes`, `add-playground-web`.
