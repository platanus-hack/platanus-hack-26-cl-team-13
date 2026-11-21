# Design

## Context

Ver proposal.md (Why). La técnica es secure multi-execution (SME) aplicada a agentes, con la garantía formal del preprint de Adams para confidencialidad. El aislamiento lo da `add-sandbox-provider`; el acceso al modelo, `add-model-gateway`; los pools de valores, `add-honeytoken-detection`. Hoy `lanes/gemelo.py` y `runner.py` son stubs.

## Goals / Non-Goals

**Goals:**
- Que la garantía dependa solo del aislamiento de red y de la sustitución de secretos, no de detectar el ataque.
- Cerrar el canal del diff con un escaneo determinista (D3).
- Un traspaso bajo → alto mínimo, suficiente para tareas que piden leer documentación.

**Non-Goals:**
- Integridad (backdoors, borrado, abuso de la allowlist): es `add-integrity-guard` (D1).
- Usar el valor verdadero hacia destinos legítimos: es `add-declassification`.
- Detectar filtraciones derivadas de la llave falsa (por ejemplo, su largo): la garantía se mantiene porque lo filtrado viene del falso; se declara como límite.

## Decisions

**Materialización de secretos fuera del sandbox.** El orquestador lee `secrets.template` (solo nombres y formatos), pide un valor verdadero y un honeytoken por secreto, y escribe el `.env` de cada gemelo antes de arrancar al agente. El bajo nunca recibe el mapa de sustitución. Alternativa descartada: sustituir dentro del sandbox; el bajo tendría ambos valores.

**Ejecución en paralelo con el mismo prompt.** Ambos gemelos arrancan a la vez desde el mismo commit. No se sincronizan paso a paso: SME no lo exige y sincronizar duplicaría la latencia.

**Traspaso como directorio de solo lectura en el alto.** El gemelo bajo deja lo que trae de la web en un directorio de traspaso (`.gemelo/untrusted/`); el orquestador lo copia al alto entre pasos, marcado como no confiable. El canal es unidireccional por construcción: el orquestador nunca copia en sentido contrario. Alternativa descartada: dejar al alto pedir URLs al bajo; abriría un canal alto → bajo con la URL como dato.

**Escaneo del diff por variantes codificadas.** Para cada valor verdadero se precalculan sus variantes en claro, base64 (con y sin padding, y sus tres alineaciones) y hex (minúsculas y mayúsculas), y se buscan en el diff completo. Es determinista y barato. Alternativa descartada: tratar el diff como salida que requiere desclasificación (opción c de D3); bloquearía casi toda tarea legítima.

**Intentos bloqueados vía hooks.** El hook `PostToolUse` del gemelo alto reporta al orquestador los comandos cuyo resultado muestra un fallo de conexión hacia un destino fuera de la allowlist; además, en local, el proxy de allowlist registra los rechazos. Se emite un evento de intento bloqueado con paso y comando.

**Tests de la tarea fuera del agente.** Al terminar el gemelo alto, el orquestador corre `tasks/<id>/tests/` dentro de su sandbox, con la red ya cortada, y registra el resultado.

## Risks / Trade-offs

- [El alto oculta el secreto con otra codificación (rot13, XOR, fragmentado en el código)] → el escaneo cubre los formatos de D3; lo demás se declara como límite y es parte del red team de F4.
- [El traspaso lleva una inyección del bajo al alto] → es contenido no confiable por diseño; la confidencialidad se mantiene porque el alto no tiene salida. La integridad es de D1.
- [Doble costo de inferencia] → asumido; las corridas son en paralelo y se usa Haiku por defecto.
- [Los gemelos divergen y el alto no resuelve la tarea] → se refleja en la métrica de utilidad, que es justamente lo que se mide.

## Open Questions

- Cuándo copia el orquestador el traspaso al alto (cada paso o solo a pedido del alto mediante un archivo de solicitud sin datos del alto). Se decide al implementar; no cambia los requisitos.
