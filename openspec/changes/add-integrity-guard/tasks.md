# Tasks

## 1. Vigilante

- [x] 1.1 Implementar el ledger con taint por fuente (pre) y por contenido (post) en `aigis/integrity.py`; verificar con `test_ledger_sources`
- [x] 1.2 Implementar la política de clases de riesgo con dos niveles; verificar con `test_bash_classes`, `test_write_classes` y `test_secret_use_only_against_allowlist`
- [x] 1.3 Implementar la consulta al monitor vía gateway, con fallo cerrado; verificar con `test_monitor_failure_fails_closed`

## 2. Integración

- [x] 2.1 Conectar el vigilante a `TwinLow` y emitir `integrity.taint` e `integrity.check`; verificar con `test_guard_blocks_backdoor_and_deletion`
- [x] 2.2 Agregar `integrity_denials` al resultado y el interruptor `AIGIS_INTEGRITY_GUARD`; verificar con `test_without_guard_twin_delivers_nothing`
- [x] 2.3 Heurística de integridad en el gateway stub para tests y demo sin crédito
- [x] 2.4 Mostrar los eventos del vigilante en la web (`apps/web/lib/events.ts`)

## 3. Benchmark

- [x] 3.1 Tarea `verify-webhook` con agente con guion engañado (bypass y borrado de tests) y tests ocultos que detectan el bypass; verificar con `test_clean_run_delivers[verify-webhook]`
- [ ] 3.2 Corrida con Claude Code real y Haiku como monitor sobre `verify-webhook` con el ataque en el README; registrar falsos positivos

## Workflow follow-up

- Archivar el cambio cuando todas las tareas estén completas.
