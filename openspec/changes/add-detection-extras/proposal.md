# Proposal

## Why

La revisión del plan contra el código dejó cuatro huecos de detección y de medición:

- Una llave partida en varias peticiones al atacante no se detectaba: cada petición se escaneaba sola (escenario 3.3 de `add-honeytoken-detection`).
- La alerta real de canarytokens solo suena si alguien *usa* la llave, y nadie la usaba (escenario 4.2).
- No había forma de medir cuánto aporta cada pieza del Gemelo (ablaciones de la fase F3).
- La demo mostraba veredictos, pero no la cadena que llevó a cada uno.

Además, tener dos gemelos permite algo que ningún monitor tiene: comparar paso a paso dos ejecuciones que solo difieren en los valores de los secretos y en la red. Es un chequeo empírico de no interferencia, que es la propiedad que prueba el preprint de Adams.

## What Changes

- **Fragmentos entre peticiones:** el tracker de filtraciones guarda los tokens de las últimas peticiones al atacante y reconstruye las llaves partidas.
- **Disparo de las canary:** cuando un honeytoken canary llega al atacante, el orquestador lo usa con una llamada de solo lectura (`sts:GetCallerIdentity`) firmada con SigV4. Así suena la alerta real. Se activa con `AIGIS_CANARY_TRIGGER`.
- **Divergencia entre gemelos:** se comparan las acciones de los dos gemelos, reemplazando cada valor por el nombre de su secreto. El resultado del carril gemelo trae la similitud, el primer paso de divergencia y su causa, los hosts a los que intentó salir cada gemelo y la **fuga contrafactual**: los pasos del bajo, que tiene los secretos verdaderos, que intentaron sacar datos fuera de la allowlist después de tocar un secreto.
- **Cadena del ataque:** `GET /runs/{id}/chain` arma, desde los eventos guardados, la secuencia de etapas por carril y caja: no confiable → secreto → codificación → salida → bloqueo, detección o filtración.
- **Ablaciones:** `RunRequest.ablate` apaga piezas del Gemelo (`honeytokens`, `diff_scan`, `handoff`, `allowlist`, `low_hints`). `eval/run_eval.py` las mide con `EVAL_ABLATIONS` y escribe `ablations.json`.

## Capabilities

### New Capabilities
- `detection-extras`: fragmentos entre peticiones, disparo de canary, divergencia de gemelos, cadena del ataque y ablaciones.

### Modified Capabilities
<!-- Completa escenarios de add-honeytoken-detection (3.3 y 4.2) sin cambiar sus requisitos. -->

## Impact

- **Código:** `aigis/leaks.py`, `aigis/scanner.py`, `aigis/canary.py`, `aigis/honeytokens.py`, `aigis/divergence.py`, `aigis/chain.py`, `aigis/runner.py`, `aigis/app.py`, `aigis/models.py`, `eval/run_eval.py` y `attacks/run_matrix.py`.
- **API:** el campo `ablate` en `POST /runs`, `divergence` en el resultado del carril gemelo, `GET /runs/{id}/chain` y los eventos `twin.divergence` y `canary.trigger`.
- **Red:** solo `AIGIS_CANARY_TRIGGER=true` sale a AWS, y solo con nuestras canary.
