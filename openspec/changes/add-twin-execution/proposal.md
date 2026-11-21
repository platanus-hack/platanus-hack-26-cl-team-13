# Proposal

## Why

El Gemelo es el aporte central del proyecto: para robar una llave, el agente necesita tener la llave y salida a internet al mismo tiempo, y el Gemelo hace que nunca se junten. Corre dos copias del mismo agente sobre la misma tarea: el gemelo alto tiene internet pero solo honeytokens, y el gemelo bajo tiene los secretos verdaderos pero no tiene internet. Sin este cambio no hay carril Gemelo ni demo. El `git diff` del gemelo bajo es el único canal de salida que el diseño deja abierto, así que se protege con un escaneo (decisión D3).

## What Changes

- Un carril Gemelo que, por corrida, crea un gemelo alto (perfil de red abierto, honeytokens) y un gemelo bajo (perfil aislado, secretos verdaderos) con la misma tarea, el mismo repo y el mismo prompt, en paralelo.
- Sustitución de secretos: cada secreto declarado en `secrets.template` se materializa con un honeytoken en el alto y con su valor verdadero en el bajo. Los "valores verdaderos" son secretos sintéticos, nunca credenciales reales (decisión D2, pools en `add-honeytoken-detection`).
- Resultado de la corrida = `git diff` del gemelo bajo + lo que el gemelo alto envió a la red.
- Escaneo del diff (D3): antes de aceptar el diff, se busca cada secreto verdadero en claro, base64 y hex; si aparece, el diff se rechaza.
- Traspaso alto → bajo, en un solo sentido: el contenido que el alto trae de la web llega al bajo marcado como no confiable. Nada fluye del bajo al alto.
- Registro de intentos de salida bloqueados del gemelo bajo (tercera señal de detección).
- Los tests de la tarea se corren sobre el resultado del bajo para medir utilidad.

## Capabilities

### New Capabilities
- `twin-execution`: ejecución de una tarea en dos gemelos con separación de secretos y de red, armado del resultado y protección del canal de salida.

### Modified Capabilities
<!-- Ninguna: no hay specs existentes. -->

## Impact

- Código: `services/api/gemelo/lanes/gemelo.py`, `services/api/gemelo/runner.py`, `services/api/gemelo/hooks.py`, `sandbox/hooks/`, `services/api/tests/`.
- Depende de: `add-sandbox-provider` (perfiles de red), `add-model-gateway` (token por corrida y eventos), `add-honeytoken-detection` (pools de secretos y honeytokens).
- Formato de tareas: usa `tasks/<id>/secrets.template` y `tasks/<id>/tests/`.
- Costo: el doble de inferencia por corrida, en paralelo.
