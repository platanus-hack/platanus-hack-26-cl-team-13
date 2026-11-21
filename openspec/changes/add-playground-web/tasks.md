# Tasks

## 1. Base

- [x] 1.1 Subir a React 19 y agregar Tailwind v4, shadcn/ui, `next-themes`, tokens y fuentes; verificar `npm ci && npm run build` en limpio sin `--legacy-peer-deps`
- [x] 1.2 Mover la capa de datos (`useRunStream`, `usePoll`, `describe()`, mapas de veredicto y plantillas) a `hooks/` y `lib/`; verificar que el panel actual sigue funcionando igual

## 2. Grabaciones

- [x] 2.1 Escribir `scripts/export-run.mjs` con eventos, diffs, `--wait` y token opcional, más `make export-run`; verificar los escenarios de Gemelo rechazado y espera del canary
- [x] 2.2 Implementar el modo grabación de `useRunSource`; verificar los escenarios de reproducción progresiva y resultado reconsolidado

## 3. Vista de corrida

- [x] 3.1 Construir los componentes de la vista de corrida (carriles, cajas, atacante, alerta de canary, resultados, filtraciones, diff, log); verificar el escenario de filtración de un honeytoken
- [x] 3.2 Construir `/ataca`, `/replay` y `/replay/[id]`; verificar los escenarios de visitante sin sesión, índice de grabaciones y API apagada
- [x] 3.3 Implementar el modo en vivo y `/runs/[id]`; verificar los escenarios de carriles en vivo, reconexión y canary después del fin
  - Verificados carriles en vivo y canary después del fin. **Falta verificar la reconexión**: en local, sin Postgres, la API pierde la corrida al reiniciarse; probarla con `DATABASE_URL` o en Render.
- [ ] 3.4 Exportar al menos una corrida real a `public/replays/`; verificar que no contiene valores del pool B

## 4. Panel, landing y resultados

- [x] 4.1 Rediseñar `/panel` y `/login`, retirar el panel viejo y redirigir `/panel/runs/[id]`; verificar los escenarios de ruta protegida y lanzar con y sin sesión
- [x] 4.2 Construir la landing
- [x] 4.3 Construir `/resultados` con `summary.json`; verificar el escenario sin eval
- [x] 4.4 Revisar 400 px, temas claro y oscuro, foco visible y `prefers-reduced-motion`; verificar el escenario de pantalla de teléfono
- [ ] 4.5 Curar 3 a 5 grabaciones antes del freeze de h30
