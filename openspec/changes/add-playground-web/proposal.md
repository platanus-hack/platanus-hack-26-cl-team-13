# Proposal

## Why

El jurado tiene que entender y probar Gemelo en 3 minutos, sin ayuda. Hoy la web tiene un panel interno que funciona (lanzar corridas, ver los 4 carriles en vivo por SSE, filtraciones, diff y log), pero las páginas públicas `/`, `/ataca`, `/replay` y `/resultados` son stubs. Además, sin una forma de reproducir corridas sin la API, la demo depende de que E2B, el gateway y el presupuesto funcionen en el escenario.

## What Changes

- Rediseño completo de la web con un sistema visual único: React 19, Tailwind v4 y shadcn/ui, con tokens semánticos del dominio (filtró, honeytoken, entregado, bloqueado, contaminado) y tema oscuro por defecto.
- Una sola **vista de corrida** que sirve para una corrida en vivo y para una grabación: 4 carriles, las 5 cajas, lo que le llegó al atacante, la alerta de canary, resultados, filtraciones, diff y log.
- **Grabaciones**: un script exporta una corrida terminada (estado final, eventos y diffs) a un JSON estático que la web reproduce sin API ni sesión. Es el plan B en el escenario.
- Páginas públicas: landing, `/ataca` (galería de grabaciones), `/replay/[id]` y `/resultados`.
- Lanzar en vivo exige la sesión del panel. `/runs/[id]` reemplaza a `/panel/runs/[id]`, que queda como redirect.
- La vista en vivo sigue escuchando después de que la corrida termina, para mostrar alertas de canary tardías.
- **Vocabulario**: en el backend, `replay` es un modo del gateway que reejecuta desde `cassettes/` y necesita la API. En la web, **grabación** es un JSON estático que se reproduce sin API. Son cosas distintas y la UI muestra ambas por separado.
- Fuera de alcance: cambios en la API. Los problemas que encontramos ahí quedan anotados en design.md para P1 y P2.

## Capabilities

### New Capabilities
- `playground-web`: páginas, acceso, vista de corrida en vivo y requisitos visuales de la web.
- `run-recording`: formato de una grabación, cómo se exporta desde la API y cómo se reproduce en la web.

### Modified Capabilities
<!-- Ninguna: run-events se consume tal como está definido en add-model-gateway. -->

## Impact

- Código: `apps/web/` completo (páginas, componentes, hooks, estilos), `apps/web/scripts/export-run.mjs`, `Makefile` (target `export-run`), `apps/web/public/replays/`, `apps/web/public/results/`.
- Dependencias nuevas en `apps/web`: React 19, Tailwind v4, shadcn/ui (Radix), `next-themes`, `lucide-react`.
- Lo consume: el pitch y el guion de la demo (P4/P5).
- Depende de: `add-model-gateway` (`run-events`), `add-twin-execution`, `add-honeytoken-detection` y, para `/resultados`, `add-eval-harness` (`summary.json`).
