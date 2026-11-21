# Proposal

## Why

La demo tiene que mostrar que el ataque ocurrió: que en el carril sin defensa salió la llave y que en el Gemelo al atacante le llegó una llave falsa que suena la alarma. Sin detección no hay evidencia ni métrica de filtración para la tabla. Además, la decisión D2 exige que las "llaves verdaderas" sean secretos sintéticos, porque en el carril sin defensa llegan al atacante y en modo `record` quedan en `cassettes/`, que va a git.

## What Changes

- Dos pools de valores con formato real y sin intersección: secretos sintéticos ("verdaderos") y honeytokens (decisión D2, obligatoria).
- Honeytokens únicos por corrida, carril y gemelo, para atribuir cada detección.
- Canary tokens AWS de canarytokens.org dentro del pool de honeytokens, cargados desde un archivo fuera de git.
- Servidor atacante (sink público) que registra todo lo que recibe y lo pasa por decodificadores: en claro, base64, hex y fragmentos repartidos en varias peticiones.
- Atribución de cada detección al carril, gemelo y paso; clasificación en honeytoken (falsa) o secreto verdadero (filtración real del carril).
- Alerta del canary: webhook validado y, como respaldo, el atacante intenta usar la llave recibida para disparar la alerta.

## Capabilities

### New Capabilities
- `secret-pools`: generación y gestión de los valores sintéticos verdaderos y de los honeytokens.
- `honeytoken-detection`: recepción en el servidor atacante, decodificación, atribución y alertas de canary.

### Modified Capabilities
<!-- Ninguna: no hay specs existentes. -->

## Impact

- Código: `services/api/gemelo/honeytokens.py`, `services/attacker/{sink,decoders}.py`, endpoint de webhook en la API, `.gitignore`, `.env.example` (`CANARY_WEBHOOK_SECRET`).
- Datos: el pool de secretos sintéticos puede commitearse; los canary tokens no (un scanner que los encuentre en un repo público dispararía alertas falsas).
- Lo consumen: `add-twin-execution` (materialización de secretos), `add-baseline-lanes`, `add-eval-harness` (métrica de filtración), `add-playground-web` (panel del atacante y alarma).
