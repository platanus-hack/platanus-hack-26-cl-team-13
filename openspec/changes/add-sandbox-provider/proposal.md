# Proposal

## Why

Todos los carriles (sin defensa, monitor, FIDES y Gemelo) corren Claude Code real dentro de sandboxes desechables, y la garantía del Gemelo depende de que la red del gemelo bajo **no** pueda salir a internet. Hoy `services/api/gemelo/providers/` solo tiene stubs: sin una capa de sandbox con aislamiento de red verificable no se puede construir ni probar ningún carril. Es el primer bloque de la fase 0 (checkpoint h10).

## What Changes

- Una interfaz única de proveedor de sandboxes, elegida con `SANDBOX_PROVIDER` (`local` | `e2b`), que el orquestador usa sin saber qué proveedor hay detrás.
- Proveedor `local` sobre Docker: redes separadas `egress` (con salida) e `internal` (sin salida, solo alcanza el gateway).
- Proveedor `e2b` sobre microVMs de E2B: bloqueo total de salida y apertura de destinos puntuales.
- Perfiles de red por sandbox: abierta, solo gateway + allowlist, y corte en caliente (para el carril FIDES, decisión D5: todo menos el gateway).
- Plantilla de sandbox: Node 22, Claude Code, git, Python, el repo de la tarea y los hooks.
- Una suite de conformidad que ambos proveedores deben pasar (los mismos tests).
- **Criterio de corte D6 (decidido)**: si en h16 E2B no pasa la suite de conformidad, producción usa solo el carril Gemelo en E2B y los demás carriles quedan en local con replay. Este cambio deja la suite lista para evaluar el criterio en h16.

## Capabilities

### New Capabilities
- `sandbox-provider`: ciclo de vida de sandboxes (crear, ejecutar, leer archivos, destruir) y políticas de red por sandbox, con implementaciones intercambiables.

### Modified Capabilities
<!-- Ninguna: no hay specs existentes. -->

## Impact

- Código: `services/api/gemelo/providers/{__init__,local,e2b}.py`, `sandbox/Dockerfile`, `docker-compose.yml`, `Makefile` (`sandbox-image`, `test`), `services/api/tests/`.
- Dependencias: SDK de Docker y SDK de E2B para Python; Docker local en cada máquina de desarrollo.
- Variables: `SANDBOX_PROVIDER`, `E2B_API_KEY` (solo en el orquestador).
- Límites externos: plan gratis de E2B (10 sandboxes simultáneos, 1 h por sandbox).
- Lo consumen: `add-twin-execution`, `add-baseline-lanes`, `add-declassification`.
