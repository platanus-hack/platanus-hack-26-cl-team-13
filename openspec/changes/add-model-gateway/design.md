# Design

## Context

Ver proposal.md (Why). Claude Code permite redirigir su tráfico al modelo con `ANTHROPIC_BASE_URL`, así que el gateway puede interponerse sin modificar al agente. En producción el gateway y el orquestador corren en el mismo servicio de Render; los sandboxes de E2B lo alcanzan por su URL pública, por eso el token es la única barrera y está presente en sandboxes con internet (motivo de D4). Hoy `gateway.py` es un stub y `.env.example` usa `ANTHROPIC_API_KEY`/`GATEWAY_MODE`.

## Goals / Non-Goals

**Goals:**
- Proxy transparente para Claude Code headless (`claude -p --output-format stream-json`), incluido streaming.
- Autenticación por corrida, corte de gasto y replay determinista.
- Un contrato de eventos estable para el resto del sistema.

**Non-Goals:**
- Tope por persona, panel de gasto y cupo de corridas por hora (F3, se agregan en un cambio posterior).
- Lógica de carriles y de detección; aquí solo se define cómo se emiten sus eventos.

## Decisions

**Token por corrida, firmado y revocable.** Al crear la corrida, el orquestador pide al gateway un token opaco aleatorio ligado a `(run_id, propósito, tope_usd)` y guardado en la base. Al terminar la corrida se marca revocado. Alternativa descartada: JWT con expiración por tiempo; no se puede revocar exactamente al terminar la corrida sin una lista de revocación, que es lo mismo que guardar el token.

**Identificación de carril y gemelo.** El token es por corrida; el carril y el gemelo viajan en un header propio que el orquestador fija en el entorno de cada sandbox. El gasto se cobra al token (tope D4) y se atribuye al carril para el registro. Un header falsificado solo cambia la atribución dentro de la misma corrida, nunca el tope.

**Costo estimado a partir del uso.** Se calcula con los tokens de entrada y salida que devuelve la API y una tabla de precios en configuración, marcada "por verificar" hasta citar la página de precios.

**Casetes por corrida y carril.** Un archivo JSON por `(corrida, carril, gemelo)` con la secuencia de pares petición/respuesta, sin headers de autenticación. El replay usa un cursor por secuencia. Alternativa descartada: emparejar por hash del prompt; Claude Code incluye contenido variable (fechas, rutas) que rompe los hashes.

**Streaming de respuestas.** El gateway reenvía el stream SSE de Anthropic tal cual en `live`/`record` y lo reconstruye desde el casete en `replay`, para que Claude Code no note diferencia.

**Eventos en Postgres más fan-out SSE.** Cada evento se inserta en la base y se publica a los suscriptores de la corrida (sse-starlette). La consulta posterior lee de la base. Alternativa descartada: solo en memoria; se perdería el replay de la web y la tabla de resultados.

**Tráfico no esencial.** Se fija `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` en los sandboxes para que Claude Code solo hable con el gateway; se confirma en el spike con una captura de red.

## Risks / Trade-offs

- [El token se filtra desde un sandbox con internet] → expira al terminar la corrida y tiene tope propio en USD (D4); el daño máximo es ese tope.
- [Claude Code hace llamadas que el gateway no conoce (telemetría, otros endpoints)] → variable de tráfico no esencial más rechazo explícito de rutas desconocidas; se verifica en el spike.
- [Replay desincronizado si el agente hace un número distinto de llamadas] → error explícito de casete agotado; la web cae a la corrida grabada completa.
- [Precios sin fuente] → tabla configurable marcada "por verificar".

## Migration Plan

- Renombrar en `.env.example` `ANTHROPIC_API_KEY` → `ANTHROPIC_KEY_DEMO`/`_EVAL`/`_DEV_1` y `GATEWAY_MODE` → `MODEL_MODE`, agregando `BUDGET_CAP_USD_*`. No hay código que dependa de los nombres antiguos.

## Open Questions

- Monto por defecto del tope por token: se fija tras medir el costo de una corrida real en el spike (estimación del plan: ~$0,05–0,10 con Haiku).
