# Spec Delta

## Purpose

Definir qué páginas tiene la web, quién puede usarlas y qué tiene que mostrar la vista de corrida para que el jurado entienda Gemelo sin ayuda.

## ADDED Requirements

### Requirement: Páginas públicas y protegidas
Las rutas `/`, `/ataca`, `/replay`, `/replay/{id}`, `/resultados` y `/login` SHALL cargar sin sesión. Las rutas `/panel` y `/runs/{id}` MUST exigir la sesión del panel y redirigir a `/login?next=<ruta>` si no la hay.

#### Scenario: Visitante sin sesión
- **WHEN** alguien sin sesión abre `/ataca`
- **THEN** ve la galería de grabaciones y ningún request de la página recibe un 401

#### Scenario: Ruta protegida sin sesión
- **WHEN** alguien sin sesión abre `/runs/r_123`
- **THEN** es redirigido a `/login?next=/runs/r_123`

#### Scenario: Índice de grabaciones
- **WHEN** alguien abre `/replay`
- **THEN** es redirigido a `/ataca`

### Requirement: Lanzar exige sesión
Lanzar una corrida en vivo SHALL requerir la sesión del panel. La web MUST decidir en el servidor si hay sesión, porque la cookie es httpOnly.

#### Scenario: Lanzar sin sesión
- **WHEN** alguien sin sesión pulsa "Lanzar en vivo" en `/ataca`
- **THEN** va a `/login?next=/ataca` y no se crea ninguna corrida

#### Scenario: Lanzar con sesión
- **WHEN** alguien con sesión envía el formulario con una tarea, un vector y un payload de hasta 8192 caracteres
- **THEN** se crea la corrida y la web navega a `/runs/{id}`

### Requirement: Vista de corrida en vivo
La vista `/runs/{id}` SHALL mostrar todos los carriles de la corrida y sus cajas actualizándose con los eventos del stream, y MUST reconectar después de un corte sin perder ni duplicar eventos.

#### Scenario: Carriles en vivo
- **WHEN** una corrida está en curso
- **THEN** cada caja muestra sus comandos y eventos de red en orden, y el carril Gemelo muestra el gemelo alto y el bajo lado a lado

#### Scenario: Reconexión
- **WHEN** el stream se corta y vuelve
- **THEN** la vista pide los eventos con `after` igual al último `seq` recibido y ningún evento aparece dos veces

### Requirement: Alerta de canary tardía
La vista en vivo SHALL seguir escuchando eventos durante 10 minutos después de que la corrida termina, y MUST mostrar una alerta de canary que llegue en ese tiempo con el veredicto actualizado.

#### Scenario: Canary después del fin
- **WHEN** llega un `leak.detected` con `source` `canary` 3 minutos después del fin de la corrida
- **THEN** la vista muestra la alerta marcada como tardía y el veredicto del carril se actualiza sin recargar

### Requirement: Lo que le llegó al atacante
La vista de corrida SHALL listar cada filtración con carril, caja, paso, canal y encoding, y MUST distinguir visualmente un secreto real (pool B) de un honeytoken (pool A).

#### Scenario: Filtración de un honeytoken
- **WHEN** el gemelo alto filtra un honeytoken en base64
- **THEN** la fila aparece marcada como honeytoken, con carril Gemelo, caja alto, el paso y el encoding `base64`

### Requirement: Ningún secreto en claro
La web MUST NOT mostrar en claro ningún valor del pool B, ni en eventos, ni en el diff, ni en una grabación.

#### Scenario: Diff de un carril que filtró
- **WHEN** se abre el diff de un carril cuyo agente escribió el secreto en un archivo
- **THEN** el valor aparece redactado

### Requirement: Legible en proyector y en teléfono
La vista de corrida SHALL dejar ver qué carril filtró y cuál no sin interactuar, y todas las páginas MUST funcionar a 400 px de ancho sin scroll horizontal de la página, en tema claro y oscuro.

#### Scenario: Pantalla de teléfono
- **WHEN** se abre `/replay/{id}` a 400 px de ancho
- **THEN** los carriles se pueden recorrer y la página no se desplaza horizontalmente

### Requirement: Resultados sin cifras inventadas
`/resultados` SHALL mostrar las cifras de `summary.json` con sus denominadores visibles, y MUST mostrar un estado vacío explícito si ese archivo no existe.

#### Scenario: Sin eval todavía
- **WHEN** no existe `public/results/summary.json`
- **THEN** la página dice que la eval aún no corrió y no muestra ninguna cifra
