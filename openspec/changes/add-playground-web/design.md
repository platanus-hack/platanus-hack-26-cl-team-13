# Design

## Context

Ver proposal.md (Why). La web es Next 15 en `apps/web`. El navegador nunca llama a la API directo: `app/api/gemelo/[...path]` reenvía con el token del servidor, y la sesión es una cookie httpOnly firmada que revisan el middleware y el proxy. El orquestador emite eventos por SSE en `/runs/{id}/events?after=<seq>`, ya redactados en `EventBus.emit`. El diff de cada carril se pide aparte en `/runs/{id}/lanes/{lane}/diff`.

## Goals / Non-Goals

**Goals:**
- Que a 3 m del proyector se lea, sin interactuar, qué carril filtró y cuál no.
- Que la demo funcione sin API, sin sesión y sin presupuesto (grabaciones).
- Una sola vista de corrida para vivo y grabación.
- Conservar la capa de datos que ya funciona: `lib/api.ts`, `lib/types.ts`, `lib/auth.ts`, `middleware.ts`, el proxy y el lector de SSE.

**Non-Goals:**
- Cambios en la API (ver "Notas para P1/P2").
- Lanzar corridas sin sesión.
- Generar la eval; `/resultados` solo lee `summary.json`.

## Decisions

**Una fuente de datos, dos modos.** `useRunSource` entrega `{ run, events, diffs, state }`. En vivo combina el SSE con relecturas de `GET /runs/{id}` (debounce de 700 ms tras eventos que cambian estado). En grabación reproduce los eventos según sus `ts` relativos. Los componentes no saben de qué modo vienen los datos. Alternativa descartada: dos vistas separadas; duplica el trabajo y la grabación dejaría de probar la vista real.

**Canary tardío.** Las alertas de canary llegan minutos después de que la corrida termina, como `leak.detected` con `data.source = "canary"` y `data.late = true`, y disparan una reconsolidación de veredictos. Cuando el stream cierra con `end`, la vista en vivo vuelve a pedir `?after=<último seq>` cada 20 s durante 10 min y relee el run si llega algo. El script de export tiene `--wait` para lo mismo.

**Reconstrucción de una grabación.** El estado se arma de forma progresiva con los tipos de evento del backend, sin mostrar el veredicto en t=0. Si un resultado llega repetido (por reconsolidación), gana el último. El costo por caja parte en 0 y se completa con `lane.result`. Tipos que consume la web: `run.start`, `run.status`, `run.result`, `run.end`, `lane.status`, `lane.result`, `sandbox.ready`, `agent.text`, `agent.end`, `tool.pre`, `tool.post`, `net.egress`, `net.cut`, `handoff`, `test.result`, `scan.result`, `leak.detected`, `error`. Un tipo desconocido se muestra como fila genérica.

**Grabaciones estáticas en `public/replays/`.** Un JSON por corrida con `meta`, `run`, `events` y `diffs`, más un `index.json` curado. Se sirven como archivos estáticos, así que no necesitan API ni sesión, pero cada grabación nueva exige redeploy: se curan antes del freeze de h30. Alternativa descartada: guardarlas en Postgres y servirlas desde la API; vuelve a depender de la API, que es justo lo que el plan B evita.

**Sesión en `/ataca` desde el servidor.** La cookie es httpOnly y `api()` redirige a `/login` ante un 401, así que el cliente no puede saber si hay sesión. `/ataca` es un Server Component que llama a `validSession` y pasa `authenticated` al cliente.

**Estilos.** Tailwind v4 con shadcn/ui, que genera componentes para React 19; por eso se sube React en el mismo paso. `npm ci && npm run build` tiene que pasar sin `--legacy-peer-deps`, porque Render corre exactamente eso.

**Migración sin romper la demo.** El panel actual sigue vivo hasta que la vista nueva pase la verificación en vivo. Recién entonces se borra y `/panel/runs/[id]` redirige a `/runs/[id]`.

## Risks / Trade-offs

- [Una grabación con un secreto real en claro] → los eventos ya salen redactados del bus; el script no agrega texto propio; la verificación busca valores del pool B en el JSON.
- [Grabación sin el canary tardío] → `--wait` en el export.
- [La vista en vivo pierde eventos al reconectar] → `?after=<seq>` y descarte por `seq`, como el lector actual.
- [Peer deps de React 19 rompen `npm ci` en Render] → se valida en limpio al hacer el setup.

## Notas para P1/P2 (fuera de este cambio)

- La API responde sin token a `GET /runs`, `/runs/{id}`, `/runs/{id}/events` y `/runs/{id}/lanes/{lane}/diff`. Si la URL de `gemelo-api` es pública, cualquiera lee payloads y autores. Propuesta: exigir el token también en los GET. El proxy y el script de export ya lo mandan.
- El diff se redacta al pedirlo con `registry.pairs()`, que vive en memoria. Tras reiniciar la API, un diff guardado en Postgres saldría sin redactar. Propuesta: redactarlo al guardarlo.
- Por el mismo registro en memoria, una alerta de canary que llegue después de reiniciar la API se pierde (`by_canary` no encuentra el secreto). Propuesta: persistir el registro.
- El README de la API usa `.venv/Scripts/python -m uvicorn`, una ruta de Windows. Propuesta: unificar con `uv run uvicorn`.
