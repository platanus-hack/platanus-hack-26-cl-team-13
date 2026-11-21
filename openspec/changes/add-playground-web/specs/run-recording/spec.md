# Spec Delta

## Purpose

Definir las grabaciones: corridas terminadas exportadas a un archivo estático que la web reproduce sin API ni sesión. No confundir con el modo `replay` del gateway, que reejecuta desde `cassettes/` y necesita la API.

## ADDED Requirements

### Requirement: Formato de una grabación
Una grabación SHALL ser un JSON con `meta` (título, ataque, tarea, momento destacado), `run` (estado final), `events` (todos los eventos en orden) y `diffs` (texto o error por carril).

#### Scenario: Grabación completa
- **WHEN** se exporta una corrida terminada con 4 carriles
- **THEN** el JSON trae el run final, todos sus eventos en orden de `seq` y una entrada de diff por carril

### Requirement: Export desde la API
El script de export SHALL leer el run, los eventos y el diff de cada carril desde la API, y MUST guardar como error el diff que el Gemelo no entregó, en vez de fallar.

#### Scenario: Gemelo rechazado
- **WHEN** el carril Gemelo no entregó su diff (la API responde 409)
- **THEN** la grabación guarda para ese carril un error "no entregado" y el resto del archivo se escribe igual

#### Scenario: Espera del canary
- **WHEN** se exporta con `--wait 2m` y llega una alerta de canary durante la espera
- **THEN** la grabación incluye ese evento y el run final con el veredicto reconsolidado

### Requirement: Reproducción sin API
La web SHALL reproducir una grabación sin sesión y sin la API, incluida la pestaña de diff, y MUST NOT hacer requests a `/api/gemelo` en ese modo.

#### Scenario: API apagada
- **WHEN** la API está apagada y alguien abre `/replay/{id}`
- **THEN** la corrida se reproduce completa, se pueden ver los diffs y ningún request va a `/api/gemelo`

### Requirement: Reproducción progresiva
La reproducción SHALL respetar los tiempos relativos de los eventos, con velocidad x1 y x4 y la opción de saltar al final, y MUST NOT mostrar el veredicto de un carril antes de su evento de resultado.

#### Scenario: Inicio de la reproducción
- **WHEN** empieza la reproducción
- **THEN** ningún carril muestra veredicto hasta que se reproduce su `lane.result`

#### Scenario: Resultado reconsolidado
- **WHEN** la grabación trae dos `lane.result` para el mismo carril
- **THEN** al terminar se muestra el último

### Requirement: Distinguible de una corrida en vivo
La web SHALL marcar una grabación como tal, y MUST mostrar aparte el modo del modelo con que se corrió (`live`, `record` o `replay` de cassette).

#### Scenario: Grabación de una corrida con cassette
- **WHEN** se reproduce una grabación de una corrida con modo `replay`
- **THEN** la vista muestra el distintivo "Grabación" y, como dato aparte, que el modelo fue un replay de cassette
