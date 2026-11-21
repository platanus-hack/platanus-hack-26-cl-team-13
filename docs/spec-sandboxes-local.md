# Spec: sandboxes locales de Gemelo (DockerProvider)

Documento autocontenido para que un agente implemente, en una máquina local, las cajas donde corre Claude Code en cada carril de Gemelo. Fecha: 21 nov 2026. Dueño del orquestador: P1.

## 1. Resumen

Hay que entregar cuatro piezas que funcionen en un computador con Docker:

1. Una interfaz Python `SandboxProvider` y su implementación `DockerProvider`.
2. Una imagen `aigis-sandbox` con Claude Code headless, git, Python y hooks `PreToolUse` y `PostToolUse` que reportan al orquestador.
3. Un proxy de salida (`egress-proxy`) que aplica la política de red de cada caja: abierta, solo gateway, o allowlist.
4. Un CLI de desarrollo para crear, listar, mirar y destruir las 5 cajas de una corrida, más pruebas que demuestran el aislamiento.

La garantía que importa: **una caja con política `gw_only` no puede abrir ninguna conexión fuera del gateway y la allowlist, aunque el agente ejecute comandos arbitrarios o borre sus variables de proxy.**

Fuera de alcance: la lógica de los carriles (monitor, FIDES, traspaso alto a bajo), el gateway real (P2), Postgres (P3), el provider E2B y la web.

## 2. Contexto mínimo

Gemelo protege a Claude Code contra robo de secretos. Por cada ataque se corren 4 carriles con 5 cajas:

| Carril | Cajas | Secretos | Red inicial |
|---|---|---|---|
| Sin defensa | 1 | Pool B (sintéticos) | `open` |
| Monitor Haiku | 1 | Pool B | `open` |
| FIDES | 1 | Pool B | `open`, pasa a `gw_only` al detectar un secreto |
| Gemelo alto | 1 | Pool A (honeytokens) | `open` |
| Gemelo bajo | 1 | Pool B | `gw_only` + allowlist de la tarea |

El orquestador (FastAPI, en el host) crea las cajas con el provider, copia repo y secretos, lanza `claude -p` y recibe los hooks. Este spec cubre todo lo que pasa desde "pedir una caja" hasta "destruirla".

## 3. Topología de red

> **Actualización (implementado en `services/api/aigis/providers/local.py`):** no hay una red interna compartida. Cada caja tiene su propia red `internal: true` (`aigis-<run>-<carril>-<rol>-net`, subred /28 en 10.213.0.0/16) donde solo están ella y el proxy, y `aigis_egress` se crea con `enable_icc=false`. Con una red compartida el gemelo bajo podía mandarle el secreto al alto por IP interna y el alto sacarlo a internet sin pasar por el proxy. El test `test_boxes_cannot_reach_each_other` lo cubre. El diagrama de abajo describe la versión anterior.

```
                 internet
                    ^
                    | (solo cajas con política open y el proxy)
         +----------+-----------+
         |   red aigis_open    |  bridge normal, con salida
         +--+--------------+----+
            |              |
     cajas "open"     egress-proxy  (puertos 3128 proxy, 3129 admin)
            |              |
         +--+--------------+----+
         |   red aigis_gw      |  bridge con internal: true, SIN salida
         +--+--------------+----+
            |              |
     todas las cajas   (el host se alcanza solo vía proxy)
```

Reglas:

- **Toda caja** se conecta a `aigis_gw` y recibe `HTTP_PROXY`, `HTTPS_PROXY` y `ALL_PROXY` apuntando a `http://egress-proxy:3128`. `NO_PROXY` queda vacío.
- Las cajas con política `open` se conectan **además** a `aigis_open`, con salida directa a internet. Así el carril sin defensa es honesto: un ataque puede usar DNS, `nc` o lo que quiera.
- `aigis_gw` se crea con `internal: true`. Una caja que solo está en esa red no tiene ruta a internet ni al host. Si el agente hace `unset HTTPS_PROXY`, la conexión falla.
- El gateway del modelo y el endpoint de hooks del orquestador viven en el host. Las cajas los alcanzan **a través del proxy** en `host.docker.internal`. El proxy está en ambas redes y es el único puente.
- Pasar una caja de `open` a `gw_only` (FIDES) es: `docker network disconnect aigis_open <caja>` y cambiar su política en el proxy por la API admin. Las conexiones abiertas se cortan al desconectar la red; el proxy también cierra los túneles vivos de esa IP.

## 4. Proxy de salida (`egress-proxy`)

Proceso Python asyncio propio (no squid), porque necesitamos política por caja y eventos al orquestador. Unas 200 líneas.

**Proxy (puerto 3128, solo en las redes Docker)**

- Soporta `CONNECT host:port` (HTTPS) y HTTP plano con URL absoluta.
- Identifica la caja por la IP de origen en `aigis_gw`. IP desconocida: denegar.
- Decide según la política de esa IP:
  - `open`: permite todo.
  - `gw_only`: permite solo `GATEWAY_HOST:PORT` y `HOOKS_HOST:PORT`.
  - `allowlist`: `gw_only` más la lista de hosts de la tarea (match exacto de host o sufijo `.dominio`, nunca comodín total).
- No inspecciona TLS. La decisión se toma por host y puerto del `CONNECT`.
- Bloquea destinos a IP literal privada o link-local (`10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `127/8`) salvo los dos destinos del host, para que un agente no pivote a la LAN.
- Por cada decisión emite un evento `egress` al orquestador: `{run_id, lane, role, dest, port, decision, ts}`. Esto es lo que la web muestra como "salida bloqueada".

**Admin (puerto 3129, publicado solo en `127.0.0.1` del host)**

- `PUT /policies/{ip}` con `{run_id, lane, role, mode, allowlist}`.
- `DELETE /policies/{ip}`: borra la política y corta los túneles de esa IP.
- `GET /policies` y `GET /log?run_id=`.
- Protegido con un token de admin leído de variable de entorno. Nunca accesible desde las cajas (no escucha en las redes Docker).

## 5. Imagen `aigis-sandbox`

`sandbox/Dockerfile`, basada en `node:22-bookworm-slim`:

- Paquetes: `git`, `python3`, `python3-venv`, `curl`, `jq`, `ca-certificates`, `procps`.
- Claude Code con versión fija: `npm install -g @anthropic-ai/claude-code@<versión probada>`. Anotar la versión en el Dockerfile.
- Usuario no root `agent` (uid 1000). `--dangerously-skip-permissions` no corre como root.
- Directorios: `/workspace` (repo de la tarea), `/handoff` (entrada del traspaso, solo lectura para el bajo), `/opt/aigis` (hooks).
- `/home/agent/.claude/settings.json` horneado en la imagen con los hooks:

```json
{
  "hooks": {
    "PreToolUse":  [{ "matcher": "*", "hooks": [{ "type": "command", "command": "python3 /opt/aigis/hook.py pre",  "timeout": 30 }] }],
    "PostToolUse": [{ "matcher": "*", "hooks": [{ "type": "command", "command": "python3 /opt/aigis/hook.py post", "timeout": 30 }] }]
  }
}
```

- `settings.json` y `/opt/aigis` pertenecen a root y son solo lectura para `agent`, para que el agente no se desactive los hooks.
- **Sin secretos en la imagen.** Ni API keys, ni pools, ni tokens. Se copian al crear la caja.

### 5.1 `hook.py`

- Lee el JSON del hook por stdin y lo envía por POST a `$AIGIS_HOOK_URL/{pre|post}` con cabecera `Authorization: Bearer $AIGIS_LANE_TOKEN`. Usa el proxy del entorno.
- En `pre`, si el orquestador responde `{"decision": "deny", "reason": "..."}`, imprime en stdout:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "<reason>"}}
```

  Con `allow`, sale con código 0 sin salida.
- Si el orquestador no responde en 10 s: con `AIGIS_HOOK_FAIL=closed` niega, con `open` permite. El bajo y FIDES usan `closed`; sin defensa usa `open`.
- Solo biblioteca estándar de Python (urllib). Nada que instalar.

Verificar el formato exacto de entrada y salida de hooks contra la documentación oficial de Claude Code para la versión fijada antes de cerrar.

### 5.2 Cómo se lanza el agente

El orquestador (no este spec) ejecuta dentro de la caja, como `agent`, en `/workspace`:

```
claude -p "<tarea>" --output-format stream-json --verbose \
  --dangerously-skip-permissions --model claude-haiku-5-5
```

Con estas variables:

| Variable | Valor |
|---|---|
| `ANTHROPIC_BASE_URL` | `http://host.docker.internal:<puerto gateway>` |
| `ANTHROPIC_AUTH_TOKEN` | token de gateway del carril, por corrida y con tope |
| `AIGIS_HOOK_URL` | `http://host.docker.internal:<puerto orquestador>/hooks/{run_id}/{lane}` |
| `AIGIS_LANE_TOKEN` | token aleatorio del carril para autenticar hooks |
| `AIGIS_HOOK_FAIL` | `open` o `closed` |
| `HTTP(S)_PROXY`, `ALL_PROXY` | `http://egress-proxy:3128` |

Para pruebas sin gasto existe `AIGIS_AGENT=scripted`: en vez de `claude`, el orquestador corre `/opt/aigis/scripted_agent.py <guion.json>`, que ejecuta comandos de un guion (leer `.env`, hacer `curl` al atacante, editar un archivo) y emite eventos en el mismo formato stream-json mínimo. Así se prueban red y hooks sin tocar la API.

## 6. Interfaz `SandboxProvider`

`orchestrator/gemelo/providers/base.py`:

```python
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol

NetMode = Literal["open", "gw_only", "allowlist"]

@dataclass
class NetPolicy:
    mode: NetMode
    allowlist: list[str] = field(default_factory=list)

@dataclass
class SandboxSpec:
    run_id: str
    lane: Literal["none", "monitor", "fides", "twin_high", "twin_low"]
    image: str = "aigis-sandbox:dev"
    net: NetPolicy = field(default_factory=lambda: NetPolicy("gw_only"))
    env: dict[str, str] = field(default_factory=dict)
    cpus: float = 1.0
    memory_mb: int = 2048
    ttl_s: int = 900

@dataclass
class Sandbox:
    id: str            # id propio del provider
    spec: SandboxSpec
    ip: str            # IP en aigis_gw

@dataclass
class ExecEvent:
    stream: Literal["stdout", "stderr", "exit"]
    data: str          # una línea, o el código de salida en "exit"

class SandboxProvider(Protocol):
    async def create(self, spec: SandboxSpec) -> Sandbox: ...
    async def set_network(self, sb: Sandbox, policy: NetPolicy) -> None: ...
    async def put_files(self, sb: Sandbox, files: dict[str, bytes], mode: int = 0o600) -> None: ...
    async def get_file(self, sb: Sandbox, path: str) -> bytes: ...
    def exec(self, sb: Sandbox, cmd: list[str], env: dict[str, str] | None = None,
             user: str = "agent", cwd: str = "/workspace") -> AsyncIterator[ExecEvent]: ...
    async def destroy(self, sb: Sandbox) -> None: ...
    async def list(self, run_id: str | None = None) -> list[Sandbox]: ...
```

Reglas del contrato:

- `create` deja la caja corriendo (`sleep infinity` como proceso principal), conectada a sus redes y con su política ya cargada en el proxy **antes** de devolver. Nunca existe una caja sin política.
- `put_files` acepta rutas absolutas dentro de la caja y crea directorios. Se usa para repo, `.env` con secretos y archivos de traspaso.
- `exec` hace streaming línea a línea; el último evento es `exit`.
- `destroy` es idempotente: borra contenedor, política del proxy y volúmenes. Nunca falla si la caja ya no existe.
- La interfaz no menciona Docker. E2B la implementará después con las mismas firmas.

## 7. `DockerProvider`

`orchestrator/gemelo/providers/docker.py`, con el SDK `docker` de Python (envolver llamadas bloqueantes con `asyncio.to_thread`) o el CLI vía `asyncio.create_subprocess_exec`. Elegir uno y no mezclar.

Al crear un contenedor:

- Nombre `aigis-{run_id[:8]}-{lane}`.
- Labels `aigis.run`, `aigis.lane`, `aigis.created`, `aigis.ttl`.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit 512`, `--cpus`, `--memory`.
- `--read-only` con tmpfs en `/tmp` y volúmenes escribibles para `/workspace`, `/home/agent` y `/handoff`.
- Sin `--privileged`, sin montar el socket de Docker, sin montar carpetas del host.
- Red inicial `aigis_gw`; si la política es `open`, conectar también `aigis_open`.
- Leer su IP en `aigis_gw` y hacer `PUT /policies/{ip}` al proxy.

`set_network` a `gw_only` o `allowlist`: desconectar `aigis_open` si estaba y actualizar la política. A `open`: conectar `aigis_open` y actualizar.

`ensure_infra()` (idempotente, se llama al iniciar el orquestador): crea las dos redes si no existen, construye o verifica la imagen y levanta `egress-proxy` en ambas redes con el puerto admin publicado en `127.0.0.1:3129`.

Reaper: tarea en segundo plano que cada 60 s destruye contenedores `gemelo.*` cuyo TTL venció. Evita cajas huérfanas que consumen RAM o siguen gastando tokens.

## 8. Ver y monitorear las cajas en local

CLI `aigis-dev` (Typer o argparse) en `orchestrator/gemelo/devcli.py`:

| Comando | Qué hace |
|---|---|
| `aigis-dev infra up` / `down` | Redes, proxy e imagen. `down` borra todo lo `gemelo.*` |
| `aigis-dev run-demo [--scripted]` | Crea las 5 cajas de una corrida con sus políticas y las deja vivas |
| `aigis-dev ls [--run ID]` | Tabla: caja, carril, IP, política, estado, edad |
| `aigis-dev shell <caja>` | `docker exec -it -u agent <caja> bash` |
| `aigis-dev logs <caja>` | Sigue la salida del último `exec` |
| `aigis-dev egress [--run ID] [-f]` | Log del proxy: qué intentó salir cada caja y si pasó |
| `aigis-dev net <caja> gw_only` | Cambia la política en caliente (prueba FIDES) |
| `aigis-dev probe <caja>` | Corre las pruebas de red de la sección 10 dentro de la caja |
| `aigis-dev rm --run ID` | Destruye la corrida |

También sirve Docker Desktop: filtrar contenedores por nombre `aigis-`. Y `docker ps --filter label=aigis.run=<id>`.

El orquestador expone además `GET /dev/sandboxes` con lo mismo que `ls`, para que la web de P4 pueda pintar las cajas durante el desarrollo.

## 9. Requisitos de la máquina

**Windows 11 (máquina de Martin)**

- Docker Desktop con backend WSL2. Las cajas corren dentro de la VM de WSL2, que ya aísla del Windows host.
- `host.docker.internal` resuelve solo en Docker Desktop; en Linux nativo hay que añadir `--add-host host.docker.internal:host-gateway` al proxy. El provider lo hace siempre, no estorba.
- Agregar `.gitattributes` con `*.sh text eol=lf` y `*.py text eol=lf`: un hook con CRLF falla dentro de la caja.
- El orquestador puede correr en Windows (Python 3.12+) o dentro de WSL. Recomendado: dentro de WSL, por rendimiento de archivos y paridad con la VM de producción.
- Firewall de Windows: permitir que el gateway y el orquestador escuchen en los puertos elegidos para la interfaz de Docker.

**Linux (VM propia para la demo)**

- Docker Engine 27+. Opcional y recomendado: runtime gVisor (`runsc`) para las cajas, como capa extra contra escapes del contenedor. El provider acepta `runtime` por configuración.

**Recursos**: 5 cajas a 2 GB más proxy caben en 12 GB de RAM. Reservar 16 GB para Docker si se corren dos ataques a la vez.

## 10. Criterios de aceptación

Cada uno con su prueba en `orchestrator/tests/test_docker_provider.py`, marcada `@pytest.mark.docker`. Todas corren con `AIGIS_AGENT=scripted` y sin gastar API.

| # | Criterio | Cómo se prueba |
|---|---|---|
| A1 | Caja `gw_only` no sale a internet | `curl https://example.com` falla, con y sin `unset HTTPS_PROXY`; `curl --noproxy '*'` falla |
| A2 | Caja `gw_only` no hace DNS externo útil | `getent hosts example.com` falla o no lleva a conexión |
| A3 | Caja `gw_only` alcanza gateway y hooks | `curl $ANTHROPIC_BASE_URL/health` y POST de hook responden 200 contra stubs |
| A4 | `allowlist` permite solo lo listado | con `["pypi.org"]`: pypi.org pasa, github.com se bloquea |
| A5 | Caja `open` sale a internet directo | `curl --noproxy '*' https://example.com` responde |
| A6 | Cambio a `gw_only` en caliente | caja `open`, `set_network(gw_only)`, A1 pasa en menos de 2 s |
| A7 | No hay pivote a la LAN ni al host | `curl 192.168.x.1`, `curl host.docker.internal:<puerto no permitido>` fallan |
| A8 | Hooks llegan y pueden negar | stub del orquestador recibe `pre` y `post`; con `deny` la herramienta no se ejecuta |
| A9 | El agente no apaga los hooks | como `agent`, escribir `~/.claude/settings.json` y `/opt/aigis` falla |
| A10 | Sin secretos en la imagen | `docker history` y un grep del filesystem de la imagen no encuentran nada con forma de llave |
| A11 | 5 cajas en paralelo | `run-demo` deja 5 cajas listas en menos de 20 s con la imagen ya construida |
| A12 | Limpieza | `destroy` y `rm --run` no dejan contenedores, volúmenes ni políticas; reaper borra cajas vencidas |
| A13 | Eventos de salida | cada intento de A1, A4 y A7 aparece en `GET /log` con `decision=deny` y el carril correcto |

Prueba de humo adicional, manual y con gasto mínimo: una caja `gw_only` corre `claude -p "di hola"` contra el gateway de P2 (o un stub que reenvíe a la API) y termina con `exit 0`.

## 11. Estructura de archivos esperada

```
orchestrator/
  pyproject.toml
  gemelo/
    providers/base.py
    providers/docker.py
    devcli.py
  tests/
    stubs.py                 # stub de gateway y de hooks (FastAPI en hilo)
    test_docker_provider.py
egress_proxy/
  Dockerfile
  proxy.py
sandbox/
  Dockerfile
  settings.json
  hook.py
  scripted_agent.py
  guiones/exfil_env.json     # ejemplo: lee .env y lo manda por curl
.gitattributes
```

## 12. Reglas de seguridad para el implementador

- Nunca usar credenciales reales. Para pruebas, generar valores con formato de llave pero falsos (`sk-ant-FAKE...`, `AKIAFAKE...`).
- La API key real de Anthropic vive solo en el gateway. Ninguna caja la recibe.
- No commitear `.claude/settings.local.json` ni `.env`. Agregar `.env*` al `.gitignore`.
- El token admin del proxy y los tokens de carril se generan al iniciar y no se escriben en logs.

## 13. Preguntas abiertas

- Puertos fijos del gateway y del orquestador en local. Propuesta: gateway `8787`, orquestador `8000`, proxy `3128` y `3129`.
- Si el gateway de P2 no está listo, el stub de `tests/stubs.py` sirve para F0; no reenvía a la API.
- Versión exacta de Claude Code a fijar: la que el equipo tenga probada con `-p` y hooks hoy.
