# Spec Delta

## Purpose

Dar a los agentes de los sandboxes acceso al modelo sin exponer la API key, con autenticación por corrida, control de gasto y grabación o reproducción de respuestas.

## ADDED Requirements

### Requirement: La API key nunca sale del gateway
El gateway SHALL ser el único componente que conoce las API keys de Anthropic. Las keys MUST NOT aparecer en respuestas al sandbox, en eventos, en logs ni en casetes.

#### Scenario: Respuesta al sandbox
- **WHEN** un sandbox hace una llamada al modelo a través del gateway
- **THEN** ni el cuerpo ni los headers de la respuesta contienen la API key

#### Scenario: Casete grabado
- **WHEN** se graba una corrida en modo `record`
- **THEN** el casete en `cassettes/` no contiene la API key ni el token de la corrida

### Requirement: Token por corrida
El gateway SHALL emitir un token al crear cada corrida y aceptar solo llamadas con un token válido. Un token MUST valer únicamente para la corrida que lo emitió.

#### Scenario: Sin token
- **WHEN** llega una llamada sin token o con un token desconocido
- **THEN** el gateway responde 401 y no llama al modelo

#### Scenario: Token de otra corrida
- **WHEN** se usa el token de la corrida A para atribuir uso a la corrida B
- **THEN** el uso queda registrado solo en la corrida A

### Requirement: El token expira al terminar la corrida
El token de una corrida MUST dejar de ser válido apenas la corrida termina, por éxito, error o cancelación (decisión D4).

#### Scenario: Token usado después de la corrida
- **WHEN** alguien usa el token de una corrida ya terminada
- **THEN** el gateway responde 401

### Requirement: Tope en USD por token
Cada token SHALL tener un tope de gasto en USD propio (decisión D4). Al alcanzarlo, el gateway MUST rechazar nuevas llamadas con ese token.

#### Scenario: Tope alcanzado
- **WHEN** el gasto acumulado de un token alcanza su tope
- **THEN** la siguiente llamada con ese token se rechaza con un error de presupuesto y se emite un evento de corte

### Requirement: Modos live, record y replay
El gateway SHALL operar en el modo indicado por `MODEL_MODE`. En `live` llama al modelo; en `record` llama al modelo y guarda la corrida en `cassettes/`; en `replay` responde desde un casete sin llamar a Anthropic. El modo por defecto en local MUST ser `replay`.

#### Scenario: Replay sin red
- **WHEN** el gateway está en `replay` sin ninguna API key configurada y un agente hace llamadas
- **THEN** las respuestas salen del casete y no hay tráfico hacia `api.anthropic.com`

#### Scenario: Grabación
- **WHEN** una corrida termina en modo `record`
- **THEN** existe un casete nuevo en `cassettes/` con todas sus llamadas

### Requirement: Replay determinista por orden de llamada
En `replay`, el gateway SHALL emparejar cada llamada con la respuesta grabada en la misma posición de la secuencia de esa corrida y carril, no por hash del contenido.

#### Scenario: Prompt con variaciones
- **WHEN** la llamada número N de un replay difiere en texto de la grabada (por ejemplo, por una marca de tiempo)
- **THEN** el gateway devuelve igual la respuesta grabada número N

#### Scenario: Casete agotado
- **WHEN** un replay pide más llamadas de las que tiene el casete
- **THEN** el gateway responde un error explícito de casete agotado

### Requirement: Cuentas por propósito con corte por presupuesto
El gateway SHALL elegir la cuenta según el propósito de la corrida (demo, eval o desarrollo) y cortar las llamadas live de una cuenta al llegar al 90% de su presupuesto. Si la cuenta cortada es la de demo, las corridas de demo MUST pasar a `replay`.

#### Scenario: Corte de una cuenta de desarrollo
- **WHEN** una cuenta de desarrollo llega al 90% de su presupuesto
- **THEN** las llamadas live con esa cuenta se rechazan con un error de presupuesto

#### Scenario: Corte de la cuenta de demo
- **WHEN** la cuenta de demo llega al 90% de su presupuesto y se lanza una corrida de demo
- **THEN** la corrida corre en `replay` y la web lo indica

### Requirement: Modelo fijado por el gateway
El gateway SHALL fijar el modelo de cada llamada según su configuración (por defecto `claude-haiku-5-5`), ignorando el modelo que pida el agente.

#### Scenario: El agente pide otro modelo
- **WHEN** el agente envía una llamada pidiendo un modelo distinto
- **THEN** la llamada se hace con el modelo configurado en el gateway

### Requirement: Tope de pasos por agente
El gateway SHALL rechazar las llamadas de un agente que ya hizo el máximo de pasos configurado (por defecto 12).

#### Scenario: Paso 13
- **WHEN** un agente hace su llamada número 13 con el máximo en 12
- **THEN** el gateway la rechaza y emite un evento de tope de pasos

### Requirement: Registro de uso
El gateway SHALL registrar cada llamada con su corrida, carril, gemelo, tokens de entrada y salida, costo estimado y modo.

#### Scenario: Consulta de gasto de una corrida
- **WHEN** termina una corrida en `live`
- **THEN** su costo total se puede obtener sumando sus llamadas registradas
