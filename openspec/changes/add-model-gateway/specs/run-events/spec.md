# Spec Delta

## Purpose

Definir un formato único de eventos por corrida para que el orquestador, los carriles, la detección y la web compartan la misma vista de lo que pasó, en vivo y en replay.

## ADDED Requirements

### Requirement: Formato común de evento
Todo evento de una corrida SHALL incluir: id de corrida, carril, gemelo (si aplica), número de paso, tipo, marca de tiempo y un payload propio del tipo. Los eventos MUST NOT contener API keys ni tokens del gateway.

#### Scenario: Evento de comando
- **WHEN** el agente del carril Gemelo, gemelo alto, ejecuta un comando en su paso 3
- **THEN** se emite un evento con carril `gemelo`, gemelo `alto`, paso 3, tipo de comando y el comando en el payload

### Requirement: Tipos de evento mínimos
El sistema SHALL emitir al menos estos tipos: inicio y fin de corrida, llamada al modelo, comando del agente y su resultado, intento de red bloqueado, detección de honeytoken o de secreto, y corte (por presupuesto, tope de pasos o red).

#### Scenario: Fin de corrida
- **WHEN** termina una corrida
- **THEN** el último evento de cada carril es de fin, con el estado final del carril

### Requirement: Entrega en streaming
Los eventos de una corrida SHALL entregarse en orden por un stream SSE a medida que ocurren, y también MUST quedar persistidos para consultarlos después de la corrida.

#### Scenario: Cliente conectado en vivo
- **WHEN** la web está suscrita al stream de una corrida en curso
- **THEN** recibe cada evento en el orden en que se emitió

#### Scenario: Consulta posterior
- **WHEN** se piden los eventos de una corrida terminada
- **THEN** se obtienen los mismos eventos que se emitieron en vivo, en el mismo orden

### Requirement: Mismo stream en replay
Una corrida en `replay` SHALL emitir eventos con el mismo formato que una corrida `live`, de modo que los consumidores no necesiten distinguirlas salvo por un campo de modo.

#### Scenario: Web en replay
- **WHEN** la web muestra una corrida en `replay`
- **THEN** recibe los mismos tipos de evento que en una corrida `live`, con el modo marcado como `replay`
