# apps/web

Web de AIgis. Next.js 15 con React 19, Tailwind v4 y shadcn/ui. Spec: `openspec/changes/add-playground-web/`. Marca y tokens: `docs/design-system/`.

## Páginas

Solo `/` y `/login` son públicas. Todo lo demás vive bajo `/demo` y el middleware manda al login sin sesión (también `public/replays/` y `public/results/`). Las rutas viejas de la raíz (`/ataca`, `/panel`, `/runs/...`) redirigen a su versión bajo `/demo`.

| Ruta | Acceso | Qué es |
|---|---|---|
| `/` | Público | Landing de vitrina: marca y lista de espera, barra superior sin menú |
| `/login` | Público | Contraseña del equipo |
| `/demo` | Sesión | Cómo funciona: la tesis, el diagrama de los dos gemelos, los carriles y lo que no cubre |
| `/demo/ataca` | Sesión | Galería de corridas grabadas y formulario para lanzar en vivo |
| `/demo/replay/[id]` | Sesión | Reproduce una grabación sin API (`/demo/replay` redirige a `/demo/ataca`) |
| `/demo/resultados` | Sesión | Tabla y gráfico desde `public/results/summary.json` |
| `/demo/panel` | Sesión | Salud del orquestador, lanzar, cola, historial y comando para grabar una corrida |
| `/demo/runs/[id]` | Sesión | Corrida en vivo (`/demo/panel/runs/[id]` redirige aquí) |

La vista de corrida (`components/run/run-view.tsx`) es la misma para vivo y grabación: solo recibe `run`, `events` y `diffs`.

## Cómo habla con el orquestador

El navegador nunca llama a la API directo. `app/api/gemelo/[...path]` reenvía a `AIGIS_API_URL` con `AIGIS_API_TOKEN` desde el servidor, solo para rutas de operación (`health`, `tasks`, `queue`, `runs/...`). El SSE de `/runs/{id}/events` pasa sin buffer y con un comentario `: ping` cada 15 s. El cliente reconecta con `?after=<seq>` (`hooks/useRunStream.ts`).

Después del fin de una corrida, `/demo/runs/[id]` sigue pidiendo eventos nuevos cada 20 s durante 10 min: las alertas de canary llegan tarde (`leak.detected` con `source: "canary"` y `late: true`) y recalculan los veredictos.

La sesión es una cookie httpOnly firmada con `PANEL_SECRET` (HMAC, 3 días). La revisan el middleware y el proxy. En producción, sin `PANEL_PASSWORD`, nadie entra. En desarrollo, sin `PANEL_PASSWORD`, todo queda abierto.

## Grabaciones

Una grabación es un JSON estático en `public/replays/<id>.json` con el run final, todos los eventos y el diff de cada carril. No confundir con el modo `replay` del gateway, que reejecuta desde `cassettes/` y necesita la API.

```bash
# desde la raíz, con la API corriendo y la corrida terminada
make export-run RUN=<run_id> WAIT=2m ID=base64-readme TITLE="Ataque en base64 escondido en el README"
```

- `WAIT` espera antes de leer para capturar alertas de canary tardías.
- El script también actualiza `public/replays/index.json`, que es la galería de `/demo/ataca`. `TEST=1` marca la grabación como prueba: se ve en desarrollo, no en producción.
- Cada grabación nueva exige redeploy. Curarlas antes del freeze de h30.

## Resultados

`/resultados` lee `public/results/summary.json`. El contrato está en `lib/results.ts` (lo genera `eval/run_eval.py`):

```json
{
  "generated_at": "2026-11-21T20:00:00Z",
  "model": "claude-haiku-5-5",
  "attack_labels": { "base64": "Base64" },
  "cells": [
    { "lane": "gemelo", "attack": "base64", "n": 10, "leaks": 0, "honey_leaks": 7,
      "tests_passed": 8, "cost_usd": 0.04, "latency_s": 95 }
  ]
}
```

Una celda por carril y tipo de ataque. `n`, `leaks`, `honey_leaks` y `tests_passed` son conteos de corridas; `cost_usd` y `latency_s` son promedios por corrida. Sin el archivo, la página muestra un estado vacío.

## Local

```bash
# orquestador sin Docker ni API de Anthropic (el agente con guion no intenta filtrar)
cd services/api && AIGIS_SANDBOX_PROVIDER=fake uv run uvicorn aigis.app:app --port 8000

# web
cd apps/web
npm ci
cp .env.example .env.local   # ajusta AIGIS_API_URL, PANEL_PASSWORD y PANEL_SECRET
npm run dev                  # http://localhost:3000
```

No corras `npm run build` con `npm run dev` abierto: comparten `.next` y el servidor de desarrollo empieza a fallar.

Para probar una alerta de canary tardía en local:

1. Crea `secrets/canaries.json` en la raíz (está en `.gitignore`) con entradas como `{"canary_id": "test-1", "value": "AKIA…", "env_name": "AWS_ACCESS_KEY_ID"}` y reinicia la API. Sin ese archivo los honeytokens no tienen `canary_id` y el webhook no encuentra nada.
2. Con la corrida terminada y `/runs/<id>` abierta: `curl -X POST localhost:8000/webhooks/canary/dev-webhook-secret -H 'content-type: application/json' -d '{"canary_id":"test-1"}'`. La URL lleva el secreto de webhooks de la API, no el valor del token.

## Estilos

Siguen el sistema AIgis (`docs/design-system/`) con la paleta Egea: Egea ajustada en claro y Egea noche en oscuro (`app/globals.css`, valores de `tokens.json`). Además de los tokens de shadcn hay tokens del dominio: `leak` (fuga real, carmesí), `honey` (honeytoken, arena; nada más usa arena o ámbar), `safe` (en orden, verde azulado), `warn` (resultado parcial, violeta), `blocked` (neutro), `raised` (el carril AIgis), `twin-low` y `twin-high` (los gemelos), `terminal` y `chart-1`. Tema oscuro por defecto. El wordmark usa Inter Bold local (`app/fonts/`) por la variante `cv08`.

## Render

Servicio `aigis-web` en `render.yaml` (Node, plan starter). Corre `npm ci && npm run build`. Variables a cargar a mano: `AIGIS_API_URL` (URL pública de `aigis-api`) y `PANEL_PASSWORD`. `AIGIS_API_TOKEN` se copia de `aigis-api` y `PANEL_SECRET` lo genera Render. El proxy lee `GEMELO_*` como respaldo.
