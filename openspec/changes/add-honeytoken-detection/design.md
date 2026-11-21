# Design

## Context

Ver proposal.md (Why). El servidor atacante corre como servicio aparte en Render, en su propio dominio, y en local dentro de la red `egress` de docker compose. Los valores conocidos de cada corrida (honeytokens y secretos verdaderos, con su asignación) viven en la base de la API. Hoy `honeytokens.py`, `sink.py` y `decoders.py` son stubs.

## Goals / Non-Goals

**Goals:**
- Detección determinista de los formatos de la decisión D3 más fragmentos.
- Atribución precisa usando la asignación única por carril y gemelo.
- Una alerta de canary visible en la demo, con respaldo grabado.

**Non-Goals:**
- Detectar codificaciones arbitrarias (cifrado, XOR, rot13): se declaran como límite.
- Detectar filtraciones por otros canales que no sean el servidor atacante (DNS, otros dominios); la tabla las reporta como límite.
- La métrica agregada de filtración: es de `add-eval-harness`.

## Decisions

**Generación de los pools.** Generadores por tipo de secreto que respetan prefijo, alfabeto y largo, con semilla para reproducibilidad. El pool sintético se genera y versiona en `services/api/gemelo/data/`; los honeytokens propios se generan por corrida; los canary tokens se cargan desde `secrets/canaries.json` (ignorado por git). Alternativa descartada: generar el pool sintético en cada corrida; los casetes de replay necesitan valores estables.

**El atacante no conoce los valores.** El sink solo registra y reenvía las peticiones a la API (o la API las lee del log del sink). La decodificación y el emparejamiento con valores conocidos ocurren en la API, que es la que tiene la asignación. Así el servidor público nunca guarda el mapa de valores.

**Decodificación por variantes.** Igual que el escaneo del diff (D3): para cada valor conocido de la corrida se precalculan sus variantes en claro, base64 y hex, y se buscan en la petición completa. Además se decodifican los bloques base64/hex de la petición y se busca en el resultado, para cubrir codificaciones de envoltorios (por ejemplo, un JSON codificado). Se comparte el módulo de variantes con el escaneo del diff.

**Fragmentos por ventana de corrida.** Se concatenan, en orden, los cuerpos y queries recibidos por corrida (identificada por el honeytoken parcial o por el origen) y se busca cada valor conocido en la concatenación. Se exige que cada fragmento tenga al menos 4 caracteres para limitar falsos positivos.

**Atribución por eventos.** El valor detectado da carril y gemelo; el paso se obtiene del último evento de comando de ese gemelo anterior a la marca de tiempo de la petición.

**Canary en vivo con respaldo.** La alerta solo suena si alguien usa la llave y puede tardar minutos, así que el atacante hace una llamada de solo lectura con la llave AWS al detectarla, y la web tiene una alerta grabada como respaldo para la demo.

## Risks / Trade-offs

- [Falsos positivos en fragmentos cortos] → largo mínimo de fragmento y solo valores conocidos de la corrida.
- [La alerta de canary tarda o no llega] → disparo por el atacante y alerta grabada de respaldo.
- [Un scanner público encuentra canary tokens en el repo] → los canary tokens nunca se versionan; test que lo verifica.
- [El agente exfiltra por DNS u otro dominio] → no se detecta en este cambio; en el Gemelo la garantía se mantiene igual porque el bajo solo tiene honeytokens.

## Open Questions

- Lista exacta de tipos de secreto por tarea: la define P3 junto con las 3 primeras tareas, sin cambiar los requisitos.
