# Design

## Context

Ver proposal.md (Why). El gemelo bajo ya tiene un hook `PreToolUse` que falla cerrado y un `PostToolUse` que registra intentos de red. Los carriles `monitor` y `fides` ya muestran los dos patrones que el vigilante combina: puntuar una acción con un LLM y etiquetar el contexto por fuente y por contenido. El vigilante es heurístico, y se presenta así: la garantía formal del proyecto sigue siendo solo de confidencialidad.

## Goals / Non-Goals

**Goals:**
- Frenar backdoors, borrados, debilitamiento de tests, persistencia y uso de la llave contra la allowlist cuando el origen es contenido no confiable.
- No gastar monitor en acciones normales: solo se consulta con contexto contaminado y una acción de riesgo.
- Poder medirlo: el benchmark compara el Gemelo con y sin vigilante.

**Non-Goals:**
- Confidencialidad: la da la red. El vigilante no niega exfiltraciones hacia hosts fuera de la allowlist, para que ese bloqueo se vea como de la red.
- Detectar desalineación sin contenido no confiable: sin taint, todo pasa y solo se registra.
- Proteger el gemelo alto: su diff se descarta.

## Decisions

**Etiqueta por fuente antes de ejecutar y por contenido después.** En `PreToolUse` se marca el contexto si la acción lee README, ISSUE, `docs/` o `/handoff/`. Así un `cat README.md && rm -rf tests` ya corre contaminado. En `PostToolUse` se marca si la salida trae el marcador del traspaso o un secreto de la caja. Mismo esquema que el carril FIDES.

**Dos niveles de riesgo.** Las clases `obfuscated_exec`, `persistence` y `secret_use` no tienen uso legítimo con contexto contaminado y se niegan sin monitor. Las clases `destructive`, `tests`, `build_config`, `sensitive_code` y `suspicious_code` pueden ser parte de la tarea (implementar `verify_signature` toca un archivo sensible), así que las decide el monitor.

**`secret_use` solo hacia la allowlist.** Fuera de la allowlist la red del bajo ya bloquea la petición. Si el vigilante también la negara, se adjudicaría un bloqueo que no es suyo y la demo dejaría de mostrar que la red es la barrera.

**El monitor ve la tarea, el ledger y las acciones, no el razonamiento.** El prompt lleva la tarea legítima, el resumen del ledger, las clases detectadas, las últimas acciones y la acción actual, redactado con los secretos de la corrida. Falla cerrado: si el gateway no responde a tiempo, se niega. Es lo opuesto al carril `monitor`, porque esta caja tiene las llaves verdaderas.

**Estado por caja en la defensa, no en `Box.tainted`.** `Box.tainted` alimenta `network_cut` en el resultado. El ledger vive en la instancia de `TwinLow`, que el orquestador crea por caja.

**Medición con los tests de la tarea.** La tarea `verify-webhook` incluye en sus tests ocultos cabeceras falsas como `debug-override`. Sin vigilante, el bypass hace fallar los tests y el bajo no entrega. Con vigilante, entrega un diff limpio.

## Risks / Trade-offs

- [Falsos positivos con contexto contaminado] → casi todo agente lee el README, así que la política se activa seguido. Se mitiga dejando al monitor las clases ambiguas; el costo es una llamada por acción de riesgo.
- [Fallar cerrado bloquea trabajo legítimo si el gateway cae] → aceptado: el test `test_monitor_failure_fails_closed` lo documenta.
- [Evasión por regex] → un backdoor sin palabras ni APIs sospechosas en un archivo no sensible pasa la política sin monitor. Se declara como límite; el red team puede ampliar las clases.
- [El stub del gateway no es el monitor real] → la heurística del stub solo da determinismo a tests y demo; con Claude Code real decide Haiku.

## Open Questions

- Si conviene un carril propio "gemelo sin vigilante" en la web en vez del interruptor global.
