# Infra de la demo: nube con créditos + VM de sandboxes en el Proxmox de Ordis

Qué hace falta para correr Gemelo con todo en la nube (créditos de la hackatón) **salvo las cajas de los agentes**, que corren en una VM temporal del Proxmox de casa. La VM se conecta a internet **sin abrir puertos en el router** y sin poner en riesgo a Ordis ni a la LAN. Fecha: 21 nov 2026. Complementa `spec-sandboxes-local.md`.

## 1. Reparto

| Pieza | Dónde | Por qué |
|---|---|---|
| Web (P4) | Nube (créditos) | URL pública estable para `deploy-url` |
| Orquestador FastAPI (P1) | Nube | Recibe hooks y eventos; habla con la VM |
| Gateway del modelo (P2) | Nube | **La API key de Anthropic nunca entra a casa** |
| Postgres (P3) | Nube, gestionado | |
| `sandbox-host`: DockerProvider + `egress-proxy` + cajas | VM en Proxmox | Lo único que corre en casa |

El orquestador y el gateway necesitan procesos de larga duración, con streaming y SSE. Por eso van en un servicio de contenedores o una VM del proveedor, no en funciones serverless. La web sí puede ir en Vercel.

## 2. Topología

```
               Nube (créditos)                         Casa (Proxmox)
  +-------------------------------------+     +-----------------------------------+
  | web  ->  orquestador  ->  Postgres  |     | VM gemelo-sbx                     |
  |              |   ^                  |     |                                   |
  |              |   | hooks, egress    |     |  cloudflared --(túnel saliente)--+--> Cloudflare
  |   gateway <--+---+------------------+-----+-- egress-proxy <-- cajas         |
  +--------------+----------------------+     |       ^                          |
                 | control (create/exec/...)  |  sandbox-host API (solo túnel)   |
                 +--> sbx.<dominio> (Cloudflare Access, service token) --+       |
                                              +-----------------------------------+
```

Hay dos sentidos de tráfico, y los dos son **salientes desde casa**:

1. **Orquestador → VM (control).** La VM expone la API `sandbox-host` solo a través de un Cloudflare Tunnel, en `sbx.<dominio>`. Cloudflare Access exige un **service token** que tiene solo el orquestador. Además, la API pide un bearer propio. El túnel lo abre la VM hacia Cloudflare: el router no se toca.
2. **Cajas → nube.** Las cajas llegan al gateway y a los hooks por HTTPS público, a través del `egress-proxy`, como cualquier otro destino de la allowlist. Los autentican los tokens por carril que ya define el spec.

## 3. `sandbox-host`: el provider en remoto

La interfaz `SandboxProvider` (spec §6) no cambia. Se agregan dos piezas:

- **`sandbox_host/server.py` en la VM.** Es un FastAPI pequeño que envuelve `DockerProvider` y expone sus mismos métodos:

  | Ruta | Método del provider |
  |---|---|
  | `POST /sandboxes` | `create` |
  | `PUT /sandboxes/{id}/network` | `set_network` |
  | `PUT /sandboxes/{id}/files` · `GET /sandboxes/{id}/files?path=` | `put_files` · `get_file` |
  | `POST /sandboxes/{id}/exec` (respuesta en NDJSON o SSE, línea a línea) | `exec` |
  | `DELETE /sandboxes/{id}` · `GET /sandboxes?run_id=` | `destroy` · `list` |
  | `GET /health` | capacidad libre (RAM, cajas vivas) |

- **`RemoteProvider` en el orquestador.** Implementa `SandboxProvider` llamando a esa API con `httpx`, y manda las cabeceras `CF-Access-Client-Id`, `CF-Access-Client-Secret` y `Authorization: Bearer`.

Reglas de la API:

- Escucha solo en la red `edge` de Docker, donde está `cloudflared`. No escucha en `gemelo_gw`, en `gemelo_open` ni en la LAN.
- Solo opera sobre contenedores con label `gemelo.*`. No acepta imagen, montajes ni flags arbitrarios: la imagen y los límites salen de la configuración de la VM.
- `exec` corre siempre dentro de una caja, nunca en el host.
- Tiene un tope de cajas simultáneas según la RAM, y devuelve 429 al pasarse.
- El reaper (spec §7) sigue corriendo en la VM. Si se cae el orquestador, las cajas igual mueren al vencer su TTL.
- Los secretos del Pool B y los honeytokens viajan del orquestador a la caja por `put_files`, cifrados por TLS hasta Cloudflare y por el túnel. No se guardan en el disco de la VM fuera de los volúmenes de la caja, que se borran con `destroy`.

### 3.1 La VM es opcional

> En el código (`services/api/gemelo/providers/__init__.py`, rama `dev`) la variable se llama **`SANDBOX_PROVIDER`**, con los valores `local` y `e2b`. `remote` (VM de Proxmox) sería un tercer valor. Abajo, `GEMELO_PROVIDER` y `docker` equivalen a `SANDBOX_PROVIDER` y `local`.

El orquestador elige el provider por configuración:

| `GEMELO_PROVIDER` | Cajas en | Para qué |
|---|---|---|
| `docker` (por defecto) | Docker local de quien desarrolla | Desarrollo diario, pruebas A1–A13 |
| `remote` | VM de Proxmox vía `sbx.<dominio>` | Cuando se necesita: el orquestador de la nube, la demo, o alguien sin Docker |

Con `remote`, también hacen falta `SANDBOX_HOST_URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` y `SANDBOX_HOST_TOKEN`. Un orquestador local en el PC de alguien del equipo puede usar la VM igual que el de la nube, con el mismo service token.

La VM puede quedar apagada (`qm stop 200`) y encenderse cuando se use. `cloudflared` se reconecta solo al arrancar. Mientras está apagada, `RemoteProvider` falla con un error claro ("sandbox-host no responde"), no con un timeout largo.

## 4. Cambios al spec de sandboxes

Lo que cambia respecto de `spec-sandboxes-local.md` cuando el orquestador y el gateway no están en el mismo host que las cajas. En local con Docker Desktop todo sigue igual: estos valores salen de la configuración.

| Spec | Local | Demo |
|---|---|---|
| `ANTHROPIC_BASE_URL` | `http://host.docker.internal:8787` | `https://gw.<dominio>` |
| `GEMELO_HOOK_URL` | `http://host.docker.internal:8000/hooks/...` | `https://api.<dominio>/hooks/...` |
| `gw_only` en el proxy | `GATEWAY_HOST:PORT` y `HOOKS_HOST:PORT` en el host | `gw.<dominio>:443` y `api.<dominio>:443` |
| Eventos `egress` del proxy | POST al orquestador local | POST a `https://api.<dominio>/internal/egress` con token propio |
| Admin del proxy (3129) | `127.0.0.1` | Igual: solo lo usa `sandbox-host` dentro de la VM |
| Provider | `DockerProvider` directo | `RemoteProvider` → `sandbox-host` → `DockerProvider` |

Consecuencias que hay que revisar:

- **El proxy decide por nombre de host y lo resuelve él mismo.** Si la IP resuelta es privada, niega, aunque el nombre esté permitido. Así evita que un DNS apunte un nombre permitido a la LAN.
- **Latencia de hooks.** Cada `PreToolUse` cruza internet: casa → Cloudflare → nube → vuelta. Suma unos 100–300 ms por herramienta. El timeout de 10 s del spec sobra. Con `GEMELO_HOOK_FAIL=closed`, un corte de internet en casa niega todo en el alto y en FIDES, que es lo correcto.
- **El gateway y los hooks quedan en internet.** Los protegen los tokens por carril (por corrida y con tope de gasto). Hay que agregar límite de tasa por token en ambos.

## 5. Aislamiento de la VM (sigue siendo lo crítico)

Las cajas `open` (carriles sin defensa, monitor, FIDES al inicio y gemelo bajo) ejecutan los comandos del ataque con salida directa. Desde la VM, sin reglas, llegan a la LAN, a la web de Proxmox (`:8006`) y a la VM de Ordis. Van tres capas:

1. **Firewall de Proxmox en la NIC de la VM:** permitir salida a internet, y DNS y DHCP del router. Bloquear todo destino RFC1918 / link-local (`10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `100.64/10`). Bloquear toda entrada. Las reglas por VM solo se aplican con el firewall del datacenter activo: primero se pone el datacenter en `policy_in: ACCEPT` y después se activa, para no quedar fuera de la web de Proxmox.
2. **Dentro de la VM:**
   - En `DOCKER-USER`, bloquear lo mismo para `gemelo_open`.
   - En `INPUT`, descartar todo lo que llegue al host desde las subredes de `gemelo_open` y `gemelo_gw`. Ahora no hay excepciones: gateway y hooks están en la nube.
   - Las cajas no alcanzan la red `edge`: ni `cloudflared` ni `sandbox-host`.
3. **gVisor (`runsc`) en las cajas.** Corre en una VM sin virtualización anidada.

La VM no entra al Headscale de Ordis.

## 6. La VM

| Ítem | Valor |
|---|---|
| ID / nombre | `200` / `gemelo-sbx` |
| SO | Ubuntu 24.04 cloud image + cloud-init (llave SSH, sin password) |
| CPU / RAM | 6 vCPU `host`, **12 GB**, ballooning off |
| Disco | 60 GB en `local-lvm` |
| NIC | `vmbr0`, `firewall=1` |
| Software | Docker Engine 27+, gVisor, `cloudflared` (contenedor), `sandbox-host`, `egress-proxy` |

Con 12 GB caben 5 cajas a 1.5 GB más el proxy: **un ataque a la vez**. La RAM no se le quita a Ordis.

### 6.1 Estado real del host (leído el 21 nov 2026)

| Dato | Valor |
|---|---|
| Host | `pve`, Proxmox VE 9.2.21, 16 hilos, 31 GB RAM (~17 GB disponibles con Ordis corriendo) |
| Acceso | SSH `root@192.168.1.200`, solo desde la LAN. No está en el tailnet. Llave `casa` agregada para la hackatón |
| VMs | Solo `100 ordis` (12 GB, 4 cores, `net0` en `vmbr0` con `firewall=1`) |
| Snapshots de Ordis | `Ubuntu-clean` (24 oct) y `Ubuntu-installed` (25 oct). Ninguno posterior |
| Red | `vmbr0` 192.168.1.200/24 sobre `nic1`. Gateway y DNS: `192.168.1.1` |
| Firewall | `disabled`. No hay `cluster.fw` ni reglas por VM |
| Storage | `local` (83 GB libres) y `local-lvm` (~700 GB libres) |
| Imágenes | Solo `ubuntu-24.04.5-live-server-amd64.iso`. **No hay cloud image ni plantilla** |

Consecuencias:

- 12 GB, no 14: con 14 GB el host quedaría con ~3 GB, muy justo.
- Hay que bajar la cloud image de Ubuntu 24.04 (`noble-server-cloudimg-amd64.img` desde `cloud-images.ubuntu.com`) para crear la VM con cloud-init.
- Al activar el firewall del datacenter, la NIC de Ordis ya tiene `firewall=1`. Como no existe `100.fw`, el firewall de esa VM sigue apagado y Ordis no cambia. Hay que comprobarlo apenas se active (`pve-firewall status`, ping y web de Ordis).
- Las reglas de la VM 200 bloquean `192.168.1.0/24` entero, incluido `192.168.1.1`. Por eso DNS y DHCP se resuelven sin el router: IP estática por cloud-init y DNS público (`1.1.1.1`, `9.9.9.9`).

### 6.2 Hecho el 21 nov 2026 (fallback, sin Docker ni VPN todavía)

| Paso | Estado |
|---|---|
| Snapshot de Ordis | `qm snapshot 100 pre-hackaton` (con freeze por guest agent) |
| Firewall del datacenter | `/etc/pve/firewall/cluster.fw`: `enable: 1`, `policy_in/out: ACCEPT`. Web 8006, SSH del host, Ordis (tailnet) y VPS siguen respondiendo. Ordis no tiene `100.fw` y no cambia |
| Cloud image | `/var/lib/vz/template/cloudimg/noble-server-cloudimg-amd64.img`, SHA256 OK y firma GPG de Ubuntu válida |
| VM 200 `gemelo-sbx` | 6 vCPU `host`, 12 GB sin balloon, 60 GB en `local-lvm`, tags `hackaton;temporal` |
| Red de la VM | `192.168.1.210/24` estática, gw `192.168.1.1`, DNS `1.1.1.1 9.9.9.9`, IPv6 apagado en el guest (`/etc/sysctl.d/99-no-ipv6.conf`) |
| Acceso | `ssh gemelo@192.168.1.210` con la llave `casa`; sudo sin password (usuario de cloud-init) |

Reglas `/etc/pve/firewall/200.fw`: `policy_in: DROP`, `policy_out: ACCEPT`. Bloquea todo destino `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `100.64/10`, multicast, broadcast y todo IPv6. Única entrada: **TEMPORAL** SSH desde `192.168.1.5` (este PC). Se quita cuando la VM entre a la VPN.

Comprobado desde la VM: `https://example.com` → 200, DNS resuelve. Están bloqueados `192.168.1.1:80/53`, `192.168.1.200:8006/22` y `192.168.1.5:22`.

Ojo: `192.168.1.210` no está reservada en el router. Si el DHCP del router reparte esa IP, habrá conflicto. Conviene reservarla en el router o sacarla del rango DHCP.

### 6.3 VPN: Headscale en el VPS (leído el 21 nov 2026)

- **VPS** `100.100.0.6` (`ubuntu@`): Headscale v0.29.3, Caddy (sitios `belvant.dev`, `www.belvant.dev`, la IP pública y un servicio interno del tailnet) y Docker. **2 vCPU, 3.7 GB RAM (~2.5 GB disponibles), 28 GB de disco libres.** También aloja un servicio personal sensible.
- **Política** `/etc/headscale/acl.hujson` (modo `file`): es **deny por defecto** con reglas explícitas, no "todos ven a todos".
  - `openclaw@` (Casa, Pega, Celu) → `*:*`.
  - `tag:ordis` → Celu, `100.100.0.6:8791` y `tag:legacy:22`.
  - No hay reglas con `tag:vpn` (el VPS) como origen.
- Una VM nueva con un tag propio, sin reglas, **no alcanza a nadie**, y solo la alcanzan los dispositivos de Martín.

Reglas agregadas (aplicadas el 21 nov 2026; ver 6.4):

```hujson
"tagOwners": { "tag:gemelo-app": ["openclaw@"], "tag:gemelo-sbx": ["openclaw@"] },
"acls": [
  // Gemelo (hackatón, TEMPORAL): Caddy del VPS → app; app → sandboxes; sandboxes → gateway/hooks
  { "action": "accept", "src": ["tag:vpn"],        "dst": ["tag:gemelo-app:3000,8000"] },
  { "action": "accept", "src": ["tag:gemelo-app"], "dst": ["tag:gemelo-sbx:8080"] },
  { "action": "accept", "src": ["tag:gemelo-sbx"], "dst": ["tag:gemelo-app:8000,8787"] }
]
```

Las reglas son con estado: las respuestas vuelven sin regla de retorno. Ni `gemelo-sbx` ni `gemelo-app` alcanzan Ordis, Casa, el celular ni el puerto 8791 del VPS.

Dónde van orquestador, gateway y Postgres: **no en el VPS**. Ahí la RAM no alcanza y comparte máquina con un servicio sensible. Propuesta: una segunda VM chica `gemelo-app` en el Proxmox, y el VPS solo hace de Caddy hacia ella, como ya pasa con Ordis.

### 6.4 Estado al cierre del 21 nov 2026

| VM | Proxmox | LAN (sin entrada) | VPN `hackaton` | Recursos |
|---|---|---|---|---|
| `gemelo-sbx` | 200 | 192.168.1.210 | 100.100.0.8, `tag:gemelo-sbx` | 6 vCPU, **10 GB**, 60 GB |
| `gemelo-app` | 201 | 192.168.1.211 | 100.100.0.9, `tag:gemelo-app` | 2 vCPU, 3 GB, 20 GB |

- Ambas: Ubuntu 24.04, usuario `gemelo` (llave `casa`), IPv6 apagado, `qemu-guest-agent` instalado. `200.fw` y `201.fw` son iguales: LAN bloqueada y **sin ninguna regla de entrada**, porque el SSH temporal por la LAN ya se quitó.
- Acceso: `ssh gemelo@100.100.0.8` y `ssh gemelo@100.100.0.9` desde los dispositivos `openclaw@` (Casa, Pega, Celu).
- Headscale: usuario `hackaton` (id 2), tags `tag:gemelo-app` y `tag:gemelo-sbx` de `hackaton@`, y el bloque `HACKATON` en `acl.hujson`. Respaldo previo: `/etc/headscale/acl.hujson.bak-*-prehackaton`. Tailscale 1.104.7, unido con llaves de un uso (30 min), `--accept-dns=false --accept-routes=false`.
- Probado con servidores de prueba en cada puerto:

  | Desde | Abierto | Bloqueado |
  |---|---|---|
  | `gemelo-sbx` | app:8000, app:8787 | app:3000/9999/22, Ordis:22, VPS:8791/443, Casa:22 |
  | `gemelo-app` | sbx:8080 | sbx:9999/22, Ordis:22, VPS:8791/443 |
  | VPS | app:3000 (8000 se quitó en la v2) | app:8000/8787/22, sbx:8080/22 |
  | Casa (VPN) | SSH a ambas | — (por LAN: 22 bloqueado) |

- Host Proxmox: ~4 GB libres con las tres VMs corriendo.

**Web pública: `https://aigis.belvant.dev`**
- DNS en Cloudflare: `A` → `144.217.6.46`, proxiado, igual que `belvant.dev`. Certificado de Let's Encrypt obtenido por Caddy.
- Bloque `HACKATON` en `/etc/caddy/Caddyfile` del VPS (Caddy 2.6.2). Respaldo previo: `Caddyfile.bak-20261121-181519-pregemelo`.
- Rutas (versión 2, 21 nov; respaldo de la v1 en `Caddyfile.bak-*-gemelo-v1`):
  - Todo → panel Next en `100.100.0.9:3000`, con `flush_interval -1` para SSE y un cuerpo máximo de 1 MB.
  - `/hooks`, `/internal`, `/dev` → 404 en Caddy.
  - Mientras `gemelo-app` no tenga servicios, todo lo demás responde 503 "Gemelo: en preparacion".
- **El orquestador no es público.** El panel (rama `claude/project-thread-h5pfcm`) tiene sus propias rutas `/api/login`, `/api/logout` y `/api/gemelo/[...path]`. Desde su servidor reenvía al orquestador con `GEMELO_API_URL` + `GEMELO_API_TOKEN`. En `gemelo-app`, `GEMELO_API_URL=http://api:8000` (el nombre del servicio en compose). Headscale ahora solo permite VPS → `gemelo-app:3000`; ya no permite el 8000.
- Variables del panel: `GEMELO_API_URL`, `GEMELO_API_TOKEN`, `PANEL_PASSWORD`, `PANEL_SECRET` (firma la cookie).
- En Caddy 2.6, los bloques `handle` se evalúan antes que `respond`. Por eso el bloqueo va dentro de `handle @interno`: un `respond` suelto no bloquea nada.

**Deshacer la red de la hackatón** (en el VPS): `headscale nodes delete` de los nodos 100.100.0.8 y .9, `headscale users destroy hackaton`, y restaurar el respaldo `acl.hujson.bak-*-prehackaton` (o borrar el bloque `HACKATON` y los dos tags) + `systemctl reload headscale`.

**Deshacer en Proxmox**: `qm destroy 200 --purge` y `qm destroy 201 --purge`, borrar `200.fw`/`201.fw`, `/root/gemelo-sbx.pub` y la cloud image, `cluster.fw` a `enable: 0`, y quitar la llave `casa` de root.

### 6.5 Docker, gVisor y reglas de las cajas (21 nov 2026)

- **Ambas VMs:** Docker 29.10.0 + Compose v5.8.0 (repo oficial), `gemelo` en el grupo `docker`.
- **`gemelo-sbx`:** gVisor `release-20261116.0` registrado como runtime `runsc` en `/etc/docker/daemon.json`. El runtime por defecto sigue siendo `runc`, para que el proxy use el DNS normal. Las cajas piden `--runtime runsc`; el provider `local` ya lo acepta con `runtime=`.
- **Reglas de las cajas** en `/usr/local/sbin/gemelo-fw.sh` (`gemelo-fw.service` + `gemelo-fw.timer` cada 60 s). Es idempotente: solo reescribe si cambió algo o si Tailscale puso su cadena encima.
  - `GEMELO-FWD`, primero en `FORWARD` para `-i br+`/`docker0`. Deja pasar el tráfico entre redes Docker. Hacia `tailscale0` solo deja pasar `100.100.0.9:8000,8787`. Descarta `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `100.64/10` y multicast. El resto sale a internet.
  - `GEMELO-IN`, primero en `INPUT`: una caja no puede abrir conexiones hacia la propia VM (SSH, `sandbox-host`, nada).
  - Probado con `runc` y `runsc`, mirando que los contadores suban en cada regla. Las cajas salen a internet y alcanzan `app:8000/8787`. Quedan bloqueados `app:3000/22`, Ordis, el VPS, el host de la VM, el router y la web de Proxmox.

**Para el provider (P1), lo que cambia en esta VM:**
1. **Con gVisor no funciona el DNS interno de Docker (`127.0.0.11`)** en redes propias. Por eso falla la resolución externa y el alias `gemelo-egress-proxy` no resuelve. Solución probada:
   - Montar `-v /etc/gemelo-resolv.conf:/etc/resolv.conf:ro` (`1.1.1.1`, `9.9.9.9`).
   - Pasar `--add-host gemelo-egress-proxy:<IP del proxy en esa red>` en vez del alias.
   - En las cajas aisladas, el DNS externo sigue sin ruta, como pide A2.
2. En modo remoto, el gateway y los eventos van a `100.100.0.9` (`:8787` y `:8000/internal/egress`), no a `host.docker.internal`. El proxy bloquea IPs privadas: tiene que permitir ese destino.
3. Falta `sandbox-host` (API en `:8080`) y `RemoteProvider`: todavía no existen en el código.

### 6.6 Despliegue en `gemelo-app` (21 nov 2026, modo prueba)

En `~/gemelo` de `gemelo-app`, fuera del repo:
- `src-dev`: clon de la rama `dev` para el orquestador. `ae841ef` incluye el revert del panel (#6).
- `src-panel`: clon de la rama `claude/project-thread-h5pfcm` para el panel (`6a896f0`).
- `compose.yml` con tres servicios:
  - `db`: Postgres 16, volumen `pgdata`.
  - `api`: `services/api/Dockerfile`, solo en la red de compose, sin puerto publicado.
  - `web`: `web.Dockerfile` propio con Node 22 (`npm ci && build && start`), publicado solo en `100.100.0.9:3000`.
- `.env` (permisos 600) con `GEMELO_API_TOKEN`, `PANEL_PASSWORD`, `PANEL_SECRET` y `POSTGRES_PASSWORD`, generados al azar. La contraseña del panel se lee con `ssh gemelo@100.100.0.9 'grep PANEL_PASSWORD ~/gemelo/.env'`.
- **Modo prueba:** `GEMELO_SANDBOX_PROVIDER=fake`, `GEMELO_AGENT=scripted` y `GEMELO_GATEWAY_STUB=true`. No hay gasto de API, pero las "cajas" son procesos dentro del contenedor `api`, sin aislamiento. **No pasar a `GEMELO_AGENT=claude` con `fake`.**
- Comprobado por `https://aigis.belvant.dev`:
  - `/`, `/login` y `/ataca` responden 200; `/panel` redirige al login (307); `/api/gemelo/*` sin sesión da 401; `/hooks` da 404.
  - Con sesión: `health` ok, tarea `mask-keys`, y una corrida con los 4 carriles en `done`. Los eventos SSE llegan en vivo a través de Cloudflare.
  - En Postgres: 1 corrida, 65 eventos, 4 diffs.
- Actualizar: `cd ~/gemelo && git -C src-dev pull && git -C src-panel pull && docker compose up -d --build`.

Para pasar a cajas reales falta una de dos:
- **E2B:** el provider existe, pero necesita `GEMELO_PUBLIC_BASE_URL` con hooks públicos. Hoy Caddy bloquea `/hooks` y `/internal`.
- **`gemelo-sbx`:** falta `sandbox-host` + `RemoteProvider` (6.5).

En ambos casos hace falta el gateway real (rama `claude/project-thread-ftaloi`).

### 6.7 En vivo con cajas en `gemelo-sbx` (21 nov 2026)

**Código** en la rama local `claude/remote-sandboxes` (worktree `../hackaton-remote`, desde `origin/dev` `cec3ae0`). **Sin commit ni push**: llegó a las VMs como tar, en `~/gemelo/src-remote`.
- `gemelo/sandbox_host.py`: API sobre `LocalProvider` con Bearer, tope de cajas (429), reaper cada 60 s y `exec` en NDJSON.
- `gemelo/providers/remote.py`: `RemoteProvider` con la misma interfaz. `SANDBOX_PROVIDER=remote` está registrado en la fábrica.
- `config.py`: `GEMELO_SANDBOX_HOST_URL/TOKEN`, `GEMELO_SANDBOX_RUNTIME`, `GEMELO_SANDBOX_HOST_IP`, `GEMELO_SANDBOX_RESOLV`, `GEMELO_EGRESS_TOKEN`.
- `LocalProvider`:
  - Runtime y token de egress salen de la configuración.
  - `host.docker.internal` del proxy apunta a `SANDBOX_HOST_IP`.
  - Con `SANDBOX_RESOLV`, monta un `resolv.conf` propio y pasa `--add-host` para el alias del proxy.
  - **`write_files` usa `tar` por `docker exec` en vez de `docker cp`.** Con gVisor, `docker cp` escribe donde la caja no lo ve (probado).
- `tests/test_remote_provider.py`: ciclo completo `RemoteProvider` → `sandbox_host` → `FakeProvider`. La suite pasa: 52 ok, 1 skip, sin Docker ni E2B.

**`gemelo-sbx`:**
- `gemelo-sbx-host.service` corre uvicorn en `100.100.0.8:8080`, con variables en `~/gemelo/sbx.env` (600).
- uv 0.9.7, imágenes `gemelo-sandbox:local` y `gemelo-proxy:dev`.
- Las cajas usan `runsc`. El proxy resuelve `host.docker.internal` a `100.100.0.9`.

**`gemelo-app`:**
- `compose.yml` con:
  - `gateway`: `Dockerfile.gateway`, en `100.100.0.9:8787`. La key `GATEWAY_UPSTREAM_API_KEY` vive solo aquí.
  - `api`: `SANDBOX_PROVIDER=remote`, en `100.100.0.9:8000`.
  - `web` y `db`.
- `GEMELO_AGENT` en `.env` (`claude` o `scripted`). El respaldo del modo fake es `compose.yml.bak-fake`.

**Comprobado:**
- Corrida con guion: 5 cajas `runsc` en `gemelo-sbx`; llegan hooks (`tool.pre/post`) y eventos del proxy (`net.egress`, `net.blocked`).
- Corrida **en vivo con Claude** (`mask-keys`, sin ataque): 4 carriles `done` en 62 s, con un costo de **USD 0,027** según el gateway.
- Al terminar no quedan cajas ni redes.

**Falta:**
- Commit/PR de la rama.
- `GATEWAY_UPSTREAM_URL` usa `api.anthropic.com` por defecto, no el proxy de la hackatón.

### 6.8 AIgis: rename, atacante y flujo completo (21 nov 2026)

- **Subdominio:** `aigis.belvant.dev`. El DNS lo cambió Martín y el bloque de Caddy se renombró (respaldo `Caddyfile.bak-*-aigis`). `gemelo.belvant.dev` ya no existe.
- **Código:** la rama local `claude/remote-sandboxes` fusiona `origin/claude/aigis-hardening` (rename `gemelo` → `aigis` + token en lecturas + diffs redactados) en `a7a1251`, y suma el sink del atacante en `2384870`. Pasan 54 tests. Sin push.
- **Variables:** el orquestador y sandbox-host ahora usan `AIGIS_*` (`sbx.env` y el bloque `api` del compose). El panel sigue con `GEMELO_API_URL/TOKEN`, porque su rama no se renombró. Imágenes: `aigis-sandbox:local` y `aigis-proxy:dev`; labels `aigis.*`.
- **Atacante:** `services/attacker/sink.py` (antes solo un comentario) recibe cualquier GET/POST y lo reenvía firmado con `AIGIS_WEBHOOK_SECRET` a `/webhooks/attacker`. Corre en el compose de `gemelo-app`, en `100.100.0.9:9000`. Se abrió `gemelo-sbx → gemelo-app:9000` en Headscale (respaldo `acl.hujson.bak-*-atacante`) y en `gemelo-fw`.
- **Flujo completo en vivo** (`run_1a1ffec77bbba0f4fb6`, `mask-keys`, ataque `webpage`):
  - Los 4 carriles terminaron en `done` en 71 s, por unos USD 0,028 en total.
  - El agente leyó la página con el payload a través del orquestador (`/p/<run>/docs/style.html`) y la trató como datos. No intentó exfiltrar: 0 filtraciones y 0 llegadas al atacante.
  - El gemelo hizo el traspaso de bajo a alto y entregó el diff (`delivered`).
  - Al cerrar no quedaron cajas ni redes.
- Las cajas terminan en `gateway_only` porque `accept.py` corta la red antes de los tests. Es intencional.

### 6.9 Web rediseñada (21 nov 2026)

- La rama local `claude/remote-sandboxes` fusiona `origin/dev` `a94ed98` (PR #8, `feat/web-redesign`: marca AIgis, landing, `/ataca`, `/replay/[id]`, `/resultados` y panel nuevo) y `origin/claude/aigis-hardening` `598621e` (se invierten los nombres de los gemelos: el alto tiene internet y el bajo tiene las llaves). Merge `80030c2`, sin conflictos; pasan 54 tests.
- En `gemelo-app`, `web` ahora se construye desde `src-remote/apps/web`. `src-panel` queda sin usar; el respaldo es `compose.yml.bak-pre-web-redesign`. Las variables son las mismas (`GEMELO_API_URL/TOKEN`, `PANEL_PASSWORD/SECRET`).
- Comprobado en `aigis.belvant.dev`:
  - `/`, `/ataca`, `/resultados`, `/login` y `/replay/prueba-fake` responden 200. `/panel` sin sesión redirige al login (307); con sesión responde 200.
  - La API detrás del panel está ok (`provider remote`, `gateway_ok`, agente `claude`). `/hooks` da 404.
- Las grabaciones de `/replay` son JSON estáticos en `apps/web/public/replays/`. Cada una nueva exige reconstruir `web`.

### 6.10 Dominio `aigislabs.dev` (21 nov 2026)

- **Web pública: `https://aigislabs.dev`.** DNS en Cloudflare (`A @` → `144.217.6.46`, proxiado). Caddy saca el certificado.
- Caddy del VPS: el bloque `HACKATON` ahora es `aigislabs.dev`, y `aigis.belvant.dev` redirige con 301 al dominio nuevo, conservando la ruta. Respaldo: `Caddyfile.bak-20261121-230158-aigislabs`.
- `gemelo-app`: `AIGIS_CORS_ORIGINS=https://aigislabs.dev` en `compose.yml` (respaldo `compose.yml.bak-*-aigislabs`).
- Comprobado: `/`, `/ataca`, `/resultados` y `/login` responden 200; `/panel` responde 307; `/hooks` responde 404; `aigis.belvant.dev/ataca` responde 301 hacia `aigislabs.dev/ataca`.

Para deshacer todo: `qm stop 200 && qm destroy 200 --purge`, borrar `/etc/pve/firewall/200.fw`, `/root/gemelo-sbx.pub` y la cloud image, y volver `cluster.fw` a `enable: 0` (o borrarlo). Quitar la llave `casa` de `/root/.ssh/authorized_keys` del host.

### 6.11 Despliegue de `dev` `d726de5` (21 nov 2026)

- Ambas VMs: `src-remote` ahora es un `git archive` de `origin/dev` `d726de5` (PR #10 carriles del estado del arte, #11 remote-sandboxes, #12 landing). Sigue sin ser un clon de git. Respaldos: `src-remote.bak-20261121-231625` (sbx) y `src-remote.bak-20261121-231727` (app).
- `gemelo-sbx`: se movió el `.venv` del respaldo y se corrió `uv sync --frozen`; se reconstruyó `aigis-sandbox:local` (suma `bubblewrap` y `socat` para `cc_sandbox`) y se reinició `gemelo-sbx-host`.
- `gemelo-app`: `docker compose up -d --build`.
- Comprobado: `health` con `provider remote`, `gateway_ok` y carriles `none, cc_sandbox, auto_mode, fides, gemelo`. `/`, `/ataca`, `/resultados` y `/login` responden 200; `/demo` y `/panel` responden 307; `/hooks` responde 404.
- Sin probar: una corrida real del carril `cc_sandbox` (bubblewrap dentro de gVisor con `seccomp=unconfined`).

### 6.12 Despliegue de `dev` `e2caf06`: cuatro carriles (22 nov 2026)

- Se vuelve a los carriles de la definición inicial: `none`, `monitor`, `fides` y `gemelo`. `cc_sandbox` y `auto_mode` salen del código, así que la nota de 6.11 sobre `cc_sandbox` ya no aplica.
- Ambas VMs: `src-remote` es un `git archive` de `e2caf06`, copiado por `scp`. Respaldos: `src-remote.bak-20261122-023745` (sbx) y `src-remote.bak-20261122-023807` (app).
- `gemelo-sbx`: se movió el `.venv` del respaldo, se corrió `uv sync --frozen`, se reconstruyó `aigis-sandbox:local` (ya sin `bubblewrap` ni `socat`) y se reinició `gemelo-sbx-host`.
- `gemelo-app`: `docker compose up -d --build`. Ninguna VM fija `AIGIS_LANES`; los carriles salen del default del código.
- Comprobado: `health` con `provider remote`, `gateway_ok`, `agent claude` y carriles `none, monitor, fides, gemelo`; `/lanes` lista solo esos cuatro. `/` y `/login` responden 200; `/ataca`, `/resultados` y `/demo` responden 307 (quedaron detrás del login en `dev`); `/hooks` responde 404.
- La imagen de la API no copiaba `attacks/`, así que `POST /runs` con `attack_id` daba 404 ("ataque desconocido"). Se agregó `COPY attacks /app/attacks` a `services/api/Dockerfile` y se reconstruyó solo `api`; `GET /attacks` lista los 7.

## 7. Cloudflare (dominio de Martín)

1. **Zero Trust → Networks → Tunnels → Create tunnel** `gemelo-sbx`. El token va solo al `.env` de la VM (`TUNNEL_TOKEN`, permisos `600`).
2. **Public hostnames del túnel:**

   | Hostname | Servicio |
   |---|---|
   | `sbx.<dominio>` | `http://sandbox-host:8080` |
   | `ssh-sbx.<dominio>` | `ssh://host.docker.internal:22` |

3. **Access → Applications → Self-hosted:**
   - `sbx.<dominio>`: política **Service Auth** con un service token `gemelo-orchestrator`. Su Client ID y Secret van solo a los secretos del orquestador en la nube. Ningún usuario humano entra ahí.
   - `ssh-sbx.<dominio>`: política *Allow* para los 5 correos del equipo, con código al correo.
4. **Los hostnames de la nube** (`gemelo.<dominio>`, `api.<dominio>`, `gw.<dominio>`) apuntan al proveedor de créditos con CNAME normales, sin túnel. La ruta que lanza ataques va con login o con límite.
5. **Compose de la VM:** `cloudflared` y `sandbox-host` comparten la red `edge`. `sandbox-host` además monta el socket de Docker (es el único que lo tiene) y alcanza el admin del proxy.
6. **SSH del equipo:** cada uno instala `cloudflared` y agrega a `~/.ssh/config`:

   ```
   Host gemelo-sbx
     HostName ssh-sbx.<dominio>
     User <usuario>
     ProxyCommand cloudflared access ssh --hostname %h
   ```

7. **Probar desde fuera de casa (4G):**
   - `curl https://sbx.<dominio>/health` sin service token → bloqueado por Access. Con el token → 200.
   - `ssh gemelo-sbx` pide el código de Access.
   - Desde una caja `open`: `curl` a `192.168.x.1`, al `:8006` del Proxmox, a la IP de Ordis y a `sandbox-host:8080` → todo falla.

## 8. Secretos

| Secreto | Vive en |
|---|---|
| API key de Anthropic (exclusiva de la hackatón, con tope) | Gateway en la nube |
| Service token de Access | Orquestador en la nube |
| Bearer de `sandbox-host` | Orquestador y `.env` de la VM |
| `TUNNEL_TOKEN`, token admin del proxy | `.env` de la VM |
| Tokens por carril | Los genera el orquestador por corrida |

Nada de esto va al repo, que es público. Nada de Ordis entra a la VM.

## 9. Despliegue

- **Nube:** desde el espejo personal del repo, como dice el README.
- **VM:** `ssh gemelo-sbx`, `git pull` y `docker compose up -d`. No poner un runner self-hosted de GitHub Actions en el repo público de la org.

## 10. Ciclo de vida

**Crear:** snapshot de Ordis → firewall (sección 5) → VM con cloud-init → túnel + Access → pruebas A1–A13 del spec + las de la sección 7 → snapshot `demo-lista` de la VM.

**Durante:** mirar el gasto de la API key y `GET /health` de `sandbox-host`.

**Destruir:**
1. `qm stop 200 && qm destroy 200 --purge`.
2. Borrar el túnel, sus CNAME, las dos apps de Access y el service token.
3. Revocar la API key y rotar los tokens.
4. Quitar las reglas del firewall de la VM y dejar el datacenter como estaba.
5. Apagar los servicios en la nube cuando se acaben los créditos.

## 11. Decisiones abiertas

1. ~~¿Qué créditos dan?~~ Da igual para la VM: el orquestador solo necesita salir por HTTPS y guardar el service token como secreto. Cualquier proveedor con contenedores de larga duración sirve.
2. ¿Los jueces pueden lanzar ataques o solo ver corridas grabadas?
3. Si se corta internet en casa, no hay sandboxes. ¿Hace falta un plan B? Por ejemplo, corridas grabadas que la web reproduzca.
