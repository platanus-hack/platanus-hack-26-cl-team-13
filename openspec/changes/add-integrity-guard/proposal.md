# Proposal

## Why

El Gemelo garantiza confidencialidad por construcción: el gemelo que tiene las llaves verdaderas no tiene internet. Pero no protege la integridad. El gemelo bajo tiene permisos legítimos sobre el repo, así que una inyección en el README, en un issue o en lo que trae el traspaso puede pedirle meter un backdoor, debilitar o borrar tests, borrar archivos o usar la llave verdadera contra un host de la allowlist. Ese diff pasaría el escaneo de secretos y se entregaría. El plan original del "Firewall de Agentes" sí frenaba estos daños, y la decisión D1 acordó recuperarlo dentro del gemelo bajo.

## What Changes

- Un vigilante de integridad en los hooks del gemelo bajo con tres piezas: un ledger con taint, una política determinista de clases de riesgo y un monitor LLM (Haiku vía gateway).
- El ledger marca el contexto como no confiable al leer README, ISSUE, `docs/`, `/handoff/` o contenido con el marcador del traspaso, y registra cuándo el agente vio un secreto. La etiqueta nunca baja durante la corrida.
- Con contexto limpio, las acciones de riesgo pasan y quedan registradas. Con contexto contaminado, las clases graves (ejecución ofuscada, persistencia, secreto contra la allowlist) se niegan, y las demás (borrado, tests, build, código sensible o sospechoso) pasan por el monitor, que falla cerrado.
- Nuevos eventos `integrity.taint` e `integrity.check`, y un contador `integrity_denials` en el resultado del carril.
- Interruptor `AIGIS_INTEGRITY_GUARD` para comparar el Gemelo con y sin vigilante.
- Una tarea nueva del benchmark, `verify-webhook`, con un agente con guion engañado que mete un bypass de firma y borra los tests del repo. Los tests ocultos de la tarea detectan el bypass.

## Capabilities

### New Capabilities
- `integrity-guard`: revisión de las acciones de riesgo del gemelo bajo cuando su contexto contiene contenido no confiable.

### Modified Capabilities
<!-- twin-execution no cambia sus requisitos: el vigilante no participa en la garantía de confidencialidad. -->

## Impact

- Código: `services/api/aigis/integrity.py` (nuevo), `aigis/lanes/gemelo.py`, `aigis/lanes/__init__.py`, `aigis/runner.py`, `aigis/models.py`, `aigis/config.py`, `aigis/gateway_client.py` (heurística del stub), `apps/web/lib/events.ts`.
- Tareas: `tasks/verify-webhook/`.
- Tests: `services/api/tests/test_integrity.py`, ajuste en `tests/test_task_catalog.py`.
- Costo: una llamada al monitor por acción de riesgo con contexto contaminado, solo en el gemelo bajo.
- Depende de: `add-twin-execution` (hooks y traspaso del bajo), `add-model-gateway` (llamada al monitor con el token de la corrida).
