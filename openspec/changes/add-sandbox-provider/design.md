# Design

## Context

Ver proposal.md (Why). Render no permite contenedores privilegiados ni Docker dentro de Docker, así que en producción los sandboxes no pueden correr junto al orquestador: van en E2B. En local sí hay Docker. Hoy existen solo stubs en `services/api/gemelo/providers/` y un `sandbox/Dockerfile` basado en `python:3.12-slim` sin Node ni Claude Code.

## Goals / Non-Goals

**Goals:**
- Una interfaz pequeña que cubra todo lo que necesitan los carriles: crear, ejecutar, leer, cambiar red, destruir.
- Aislamiento de red aplicado por la infraestructura (red Docker o reglas de E2B), nunca por el agente.
- La misma suite de conformidad para ambos proveedores.

**Non-Goals:**
- Lógica de carriles o de gemelos (es de `add-twin-execution` y `add-baseline-lanes`).
- La desclasificación hacia destinos de la allowlist con el valor real (`add-declassification`); aquí solo existe la allowlist como lista de destinos.
- Modal como proveedor. Solo se agrega si el spike de E2B falla en F0.

## Decisions

**Interfaz `SandboxProvider`.** Operaciones: `create(template, task_repo, network) -> Sandbox`, `exec(sandbox, cmd) -> stream`, `read_file`, `git_diff`, `set_network(sandbox, profile)`, `destroy`. Se elige con una fábrica que lee `SANDBOX_PROVIDER`. Alternativa descartada: un adaptador por carril; duplicaría la lógica de red.

**Decisiones de la interfaz que no están en el memo** (tomadas al implementar el grupo 2):
- Si `SANDBOX_PROVIDER` no está definida o está vacía, se usa `local`. El spec solo exige fallar con un valor inválido, y `local` es lo seguro para desarrollar.
- Se agrega `destroy_run(run_id)`: destruye todos los sandboxes de una corrida por su etiqueta, para cumplir la limpieza garantizada aunque el proceso que los creó haya caído.
- `exec` entrega eventos `ExecOutput` (stdout o stderr) y termina con un `ExecExit` con el código de salida.
- La fábrica importa cada proveedor solo al elegirlo, para que en local no se necesite la key de E2B.

**Perfiles de red como valores, no flags.** `open`, `isolated(allowlist)` y `gateway_only`. `gateway_only` es `isolated` con allowlist vacía y es el destino del corte en caliente de FIDES (D5).

**Local: dos redes Docker.** `egress` (bridge normal) e `internal` (`internal: true`). El gateway está conectado a ambas. Un sandbox aislado solo se conecta a `internal`. Para el corte en caliente se desconecta el contenedor de `egress` y se conecta a `internal` (`docker network disconnect/connect`), lo que no reinicia el contenedor. La allowlist en local se resuelve con un proxy de salida en la red `internal` que solo reenvía a los dominios permitidos. Alternativa descartada: iptables dentro del contenedor, porque el agente podría modificarlas si tiene privilegios.

**E2B: reglas de salida del sandbox.** `denyOut: 0.0.0.0/0` más `allowOut` con el gateway y la allowlist; las reglas se pueden cambiar con el sandbox corriendo, lo que cubre el corte en caliente.

**Plantilla única.** `sandbox/Dockerfile` pasa a Node 22 con Claude Code, git y Python 3.12, y copia los hooks. En E2B se construye una plantilla equivalente desde el mismo Dockerfile. `make sandbox-image` construye la local.

**Decisiones de la plantilla que no están en el memo** (tomadas al implementar el grupo 1):
- Base `python:3.12-slim-bookworm` con Node 22 copiado desde `node:22-bookworm-slim`: Debian bookworm no trae Python 3.12.
- Claude Code fijado con `ARG CLAUDE_CODE_VERSION` (2.1.330), para que todo el equipo y E2B usen la misma versión.
- El agente corre como usuario sin privilegios `agent`, para que no pueda cambiar rutas, DNS ni firewall desde adentro (escenario "El agente no puede abrir la red").
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` y `DISABLE_AUTOUPDATER=1` en la imagen. El memo dejaba la primera como candidata a confirmar en el spike del gateway (tarea 6.1 de `add-model-gateway`).
- `curl` incluido, para el spike y los tests de red.
- `pytest` preinstalado (fijado a la versión de `services/api/uv.lock`): los tests de la tarea corren dentro del sandbox con la red cortada y no se pueden instalar en ese momento. Si una tarea necesita más dependencias, se resolverá en `add-task-fixtures`.

**Decisiones tomadas al implementar el provider local y el de E2B** (21 nov, verificadas contra docs.e2b.dev y SDK e2b 2.64.0):
- Interfaz asíncrona y `create(spec)`: el orquestador corre cinco cajas en paralelo y copia repo, ataque y secretos en orden, con los secretos fuera del commit base.
- Local: una red `internal` por caja con el proxy adentro, en vez de una red interna compartida. Con la red compartida el gemelo bajo podía pasarle el secreto al alto por IP interna. E2B ya aísla cada sandbox, así los dos providers quedan equivalentes.
- Local: el resolver embebido de Docker no responde nombres externos en redes `internal` (verificado con un test), y el proxy rechaza los destinos fuera de la allowlist antes de resolverlos.
- Plantilla de una sola etapa (Node 22 desde el tarball oficial, verificado con SHASUMS256): E2B construye desde Dockerfile pero no admite multi-stage.
- Mapeo de red en E2B: `open` sin `network`; `isolated(lista)` como `allow_out=[gateway, hooks, *lista]`, `deny_out=["0.0.0.0/0"]`, `dns_servers=[]`; `gateway_only` igual con solo gateway y hooks. El corte en caliente usa `update_network` con la configuración completa, porque reemplaza y no combina.
- DNS en E2B: con un dominio en `allow_out`, E2B abre 8.8.8.8 para todo tráfico y `deny_out` no lo cierra, lo que permitiría exfiltrar por DNS. Las cajas aisladas van con `dns_servers=[]`, el orquestador resuelve los hosts permitidos y los fija en `/etc/hosts`, y vacía `/etc/resolv.conf`. Funciona porque el filtro mira el SNI (443) o el Host (80). Queda por medir si una consulta UDP directa a 8.8.8.8 igual sale; la suite E2B lo registra.
- El filtro por dominio de E2B solo cubre HTTP en 80 y TLS en 443: gateway y hooks van en HTTPS 443. Se permiten hosts exactos, nunca comodines (en un CDN un host puede habilitar otros).
- Los tests de bloqueo miran la respuesta HTTP: en E2B una conexión bloqueada puede parecer abierta.
- Mejora posible para D4, no implementada: `network.rules` con `transform.headers` inyecta el token del gateway desde los secretos de E2B y el token nunca entra a la caja. Está en beta y E2B re-firma el TLS con su CA (Claude Code necesitaría `NODE_EXTRA_CA_CERTS`).

**Plantilla E2B versionada por contenido** (22 nov, no está en el memo). Motivo: en Render las cajas salían de una plantilla construida antes del renombre a AIgis y fallaban todos los carriles con `can't open file '/opt/aigis/scripted_agent.py'`. La plantilla se construía a mano y nadie la actualizaba cuando cambiaba `sandbox/`.
- El nombre es `aigis-sandbox-<12 hex del sha256 de sandbox/>`: rutas y contenidos, sin `__pycache__` ni `.pyc`, con CRLF normalizado a LF para que Windows y Linux den el mismo nombre. Si cambia `sandbox/`, cambia el nombre, y el orquestador nunca pide una imagen de otra versión del código.
- `python -m aigis.providers.e2b_template` construye solo si ese nombre no existe (`--force` reconstruye igual). En Render corre como Pre-Deploy Command del orquestador: si `sandbox/` no cambió, termina en segundos; si cambió, construye antes de que arranque la versión nueva. Si falla, el deploy se cancela y sigue la versión anterior.
- Al arrancar, el provider revisa que la plantilla exista (`ensure_infra`) y lo muestra en `/health` (`sandbox_template`, `template_ok`). Si falta, no tumba el arranque, pero `create` falla con un mensaje que dice cómo construirla, en vez de un error de archivo dentro de la caja.
- `E2B_TEMPLATE` sigue disponible para fijar un nombre a mano, solo para pruebas: se salta la garantía y el arranque lo advierte en el log.
- Cada cambio de `sandbox/` deja la plantilla anterior en E2B. Se borran a mano desde el dashboard; no se automatizó porque otro ambiente podría seguir usándola.
- Se corrige la marca de los DNS fijados en `/etc/hosts`: se escribía `# gemelo` y se limpiaba `# aigis`, así que al cambiar de perfil de red quedaban pins viejos.

**Limpieza garantizada.** El orquestador registra cada sandbox por corrida y los destruye en un `finally`; además, cada sandbox nace con una etiqueta de corrida y un timeout máximo (menor que 1 h en E2B) para que un proceso caído no deje sandboxes huérfanos.

**Suite de conformidad parametrizada.** Tests pytest en `services/api/tests/` marcados por proveedor; `make test` corre `local` por defecto, y `SANDBOX_PROVIDER=e2b make test` corre la misma suite contra E2B.

## Risks / Trade-offs

- [El spike de E2B falla (red, latencia o Claude Code)] → decidir en h10 el cambio a Modal, como dice el plan.
- [Mantener dos proveedores consume el tiempo de P1] → decisión D6: criterio de corte en h16. Si E2B no pasa la suite, solo el carril Gemelo corre en E2B y el resto queda en local con replay.
- [Límite de 10 sandboxes simultáneos en E2B; una corrida completa usa 5] → la cola visible se resuelve en `add-playground-web`; aquí el proveedor expone el error de cuota de forma explícita.
- [El proxy de allowlist local se comporta distinto a E2B] → la suite de conformidad prueba el comportamiento observable, no el mecanismo.
- [Diferencia de rendimiento entre Docker y microVM] → no afecta a los requisitos; se mide en F4.

## Open Questions

- Dominio y forma exacta en que el sandbox alcanza al gateway en E2B (URL pública del servicio en Render con token por corrida, ver `add-model-gateway`). Se confirma en el spike de P2.
