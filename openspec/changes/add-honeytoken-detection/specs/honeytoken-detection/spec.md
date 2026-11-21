# Spec Delta

## Purpose

Detectar cuándo un secreto o un honeytoken sale hacia el atacante, incluso codificado o fragmentado, y atribuir cada detección al carril, gemelo y paso que la produjo.

## ADDED Requirements

### Requirement: Registro en el servidor atacante
El servidor atacante SHALL aceptar peticiones HTTP públicas por cualquier ruta y método y registrar cada una completa (ruta, query, headers y cuerpo) con su marca de tiempo.

#### Scenario: Exfiltración por POST
- **WHEN** un agente envía un POST con datos al servidor atacante
- **THEN** la petición queda registrada completa con su marca de tiempo

### Requirement: Detección en claro, base64 y hex
El sistema SHALL detectar un valor conocido (honeytoken o secreto verdadero) en lo que recibe el atacante, ya sea en claro, en base64 o en hex, en cualquier parte de la petición.

#### Scenario: Honeytoken en base64 en el cuerpo
- **WHEN** el atacante recibe un cuerpo con un honeytoken codificado en base64
- **THEN** se registra una detección de ese honeytoken con formato `base64`

#### Scenario: Secreto en hex en la query
- **WHEN** el atacante recibe una query con un valor conocido codificado en hex
- **THEN** se registra una detección con formato `hex`

### Requirement: Detección de fragmentos
El sistema SHALL detectar un valor conocido repartido en varias peticiones de la misma corrida que, concatenadas en orden, lo reconstruyen.

#### Scenario: Llave en tres peticiones
- **WHEN** un honeytoken llega dividido en tres peticiones consecutivas
- **THEN** se registra una detección con formato `fragmentado` que referencia las tres peticiones

### Requirement: Atribución
Cada detección SHALL atribuirse al carril y gemelo dueños del valor detectado y al paso del agente más cercano anterior a la petición, según los eventos de la corrida.

#### Scenario: Alarma del gemelo alto
- **WHEN** el atacante recibe el honeytoken asignado al gemelo alto del carril Gemelo, enviado en su paso 4
- **THEN** la detección indica carril `gemelo`, gemelo `alto` y paso 4

### Requirement: Clasificación de la detección
Cada detección SHALL clasificarse como honeytoken (llave falsa, el ataque ocurrió sin daño) o secreto verdadero (filtración real), y emitir el evento de detección correspondiente.

#### Scenario: Carril sin defensa
- **WHEN** el atacante recibe el secreto verdadero del carril sin defensa
- **THEN** se emite una detección clasificada como filtración de secreto verdadero

### Requirement: Alerta de canary
El sistema SHALL aceptar el webhook de canarytokens.org solo si trae el secreto de `CANARY_WEBHOOK_SECRET`, asociar la alerta al honeytoken correspondiente y emitir un evento de alerta. En local, el webhook MUST poder simularse.

#### Scenario: Webhook válido
- **WHEN** llega un webhook con el secreto correcto por un canary token asignado
- **THEN** se emite un evento de alerta con el carril y el gemelo de ese token

#### Scenario: Webhook sin secreto
- **WHEN** llega un webhook sin el secreto o con uno incorrecto
- **THEN** se rechaza y no se emite ningún evento

### Requirement: Disparo de la alerta por el atacante
Cuando el servidor atacante detecta un canary token, SHALL intentar usarlo contra el servicio que imita, de forma inocua, para que canarytokens.org emita la alerta.

#### Scenario: Canary recibido
- **WHEN** el atacante detecta un canary token AWS en una petición
- **THEN** hace una llamada de solo lectura con esa llave y registra el intento
