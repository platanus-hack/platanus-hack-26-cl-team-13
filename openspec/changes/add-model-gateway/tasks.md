# Tasks

## 1. Configuración y base

- [ ] 1.1 Renombrar las variables en `.env.example` (`ANTHROPIC_KEY_DEMO`/`_EVAL`/`_DEV_1`, `MODEL_MODE`, `BUDGET_CAP_USD_*`, `DATABASE_URL`) y verificar que no quedan referencias a `ANTHROPIC_API_KEY` ni `GATEWAY_MODE` en el repo
- [ ] 1.2 Agregar Postgres y el servicio gateway a `docker-compose.yml`, con el gateway en las redes `egress` e `internal`; verificar que `docker compose up -d db gateway` levanta ambos
- [ ] 1.3 Crear en `store.py` las tablas de corridas, tokens, llamadas y eventos; verificar con un test que se crean en una base vacía

## 2. Proxy y tokens

- [ ] 2.1 Implementar el proxy `live` hacia `api.anthropic.com` con streaming y el modelo fijado por configuración; verificar con un test que una llamada con otro modelo sale con el configurado
- [ ] 2.2 Implementar emisión, validación y revocación de tokens por corrida; verificar los escenarios de sin token, token de otra corrida y token usado después de la corrida
- [ ] 2.3 Implementar el tope en USD por token y el tope de pasos por agente; verificar los escenarios de tope alcanzado y paso 13
- [ ] 2.4 Verificar con un test que ninguna respuesta, log ni evento contiene la API key

## 3. Record y replay

- [ ] 3.1 Implementar `record` con un casete por corrida, carril y gemelo, sin headers de autenticación; verificar que el casete existe y no contiene la key ni el token
- [ ] 3.2 Implementar `replay` por orden de llamada y el error de casete agotado; verificar los escenarios de prompt con variaciones, casete agotado y replay sin API key

## 4. Cuentas y gasto

- [ ] 4.1 Implementar la selección de cuenta por propósito y el registro de uso por llamada; verificar que el costo de una corrida es la suma de sus llamadas
- [ ] 4.2 Implementar el corte al 90% por cuenta y la caída a replay para la cuenta de demo; verificar ambos escenarios con presupuestos pequeños en el test

## 5. Eventos de corrida

- [ ] 5.1 Implementar el formato común de evento y su persistencia; verificar con un test que los eventos no contienen keys ni tokens
- [ ] 5.2 Implementar el stream SSE por corrida y la consulta posterior; verificar que ambos entregan los mismos eventos en el mismo orden
- [ ] 5.3 Documentar el contrato de eventos (tipos y payloads) en `services/api/README.md`; verificar que cada tipo del spec aparece documentado

## 6. Spike F0 e integración

- [ ] 6.1 Spike: Claude Code headless en un sandbox E2B, con `ANTHROPIC_BASE_URL` al gateway y `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, resuelve una tarea trivial; registrar en `design.md` caché, tamaño del system prompt y tráfico observado
- [ ] 6.2 Grabar el primer casete en `record` y reproducirlo en `replay` sin keys; verificar que los eventos de ambas corridas tienen los mismos tipos

## Workflow follow-up

- Si el spike 6.1 falla, decidir el cambio a Modal antes de h10 y actualizar `add-sandbox-provider`.
- Archivar el cambio cuando todas las tareas estén completas.
