# Tasks

## 1. Materialización de secretos

- [ ] 1.1 Definir el formato de `secrets.template` (nombre y tipo de cada secreto, sin valores) y documentarlo en `tasks/README.md`; verificar que las tareas existentes lo cumplen
- [ ] 1.2 Implementar la generación del `.env` de cada gemelo a partir de los pools; verificar con un test que el `.env` del alto solo tiene honeytokens y el del bajo solo valores sintéticos verdaderos

## 2. Carril Gemelo

- [ ] 2.1 Implementar en `lanes/gemelo.py` la creación de los dos sandboxes (alto abierto, bajo aislado) con el mismo commit y el mismo prompt, en paralelo; verificar con el agente con guion que ambos reciben el mismo prompt
- [ ] 2.2 Verificar con el agente con guion que un `curl` del bajo al atacante falla y el mismo `curl` del alto llega
- [ ] 2.3 Implementar el manejo de falla y timeout de un gemelo con destrucción de ambos sandboxes; verificar el escenario de timeout del gemelo alto

## 3. Traspaso y separación

- [ ] 3.1 Implementar el traspaso unidireccional alto → bajo por `.gemelo/untrusted/`; verificar que el bajo recibe el contenido marcado y que nada escrito por el bajo aparece en el alto
- [ ] 3.2 Verificar con un test que ningún valor verdadero aparece en el entorno, archivos, prompt ni eventos del gemelo alto

## 4. Resultado y escaneo del diff

- [ ] 4.1 Implementar el armado del resultado (diff del bajo + tráfico de salida del alto, descartando el diff del alto); verificar el escenario de corrida terminada
- [ ] 4.2 Implementar el escaneo del diff en claro, base64 (tres alineaciones, con y sin padding) y hex (minúsculas y mayúsculas); verificar con tests de diff limpio y de llave en cada formato
- [ ] 4.3 Rechazar el diff y emitir el evento de detección con el formato cuando el escaneo encuentra un valor verdadero; verificar que el diff rechazado no se publica

## 5. Señales y utilidad

- [ ] 5.1 Implementar en `sandbox/hooks/` y `hooks.py` el reporte `PostToolUse` de intentos de salida bloqueados del bajo; verificar que un `curl` bloqueado en el paso 4 genera el evento con paso y comando
- [ ] 5.2 Correr los tests de la tarea sobre el repo del bajo al terminar y registrar el resultado; verificar con una tarea cuyo guion la resuelve y otra que no

## 6. Integración

- [ ] 6.1 Checkpoint h16 en local con Claude Code real: al atacante le llega la llave falsa del alto, los tests pasan en el bajo y se graba el primer casete

## Workflow follow-up

- Archivar el cambio cuando todas las tareas estén completas.
