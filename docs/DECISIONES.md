# Decisiones del proyecto

Registro de decisiones tomadas y pendientes. Cada entrada: qué se decidió, por qué y qué se descartó.
Cuando una pendiente se resuelve, se mueve a "Decididas" con la fecha.

Última actualización: 2026-11-21

## Decididas

Se adoptó la recomendación del memo de decisiones para D1 a D7. D1 a D4 desbloquean las specs de fase 0 (h10).

| # | Decisión | Opción elegida | Por qué | Descartado | Responsable / hito | Fecha |
|---|----------|----------------|---------|------------|--------------------|-------|
| D1 | ¿Recuperar el watchdog original para cubrir integridad? | **Sí**: va dentro del gemelo bajo como un change nuevo `add-integrity-guard` | Recupera la protección contra backdoors y acciones destructivas sin sumar sandboxes. Se puede recortar si el equipo va atrasado. | No recuperarlo y declarar el hueco como limitación | P2 · h7 | 2026-11-21 |
| D2 | ¿Cuáles son las "llaves verdaderas" del gemelo bajo? | **Secretos sintéticos** con formato realista, de un pool separado de los honeytokens (**obligatorio**) | En el lane sin defensa la llave llega al atacante, y en modo `record` queda guardada en `cassettes/`, que se commitea a git. | Credenciales reales | P3 · h7 | 2026-11-21 |
| D3 | ¿Cómo se protege el `git diff` del gemelo bajo? | **Escanear el diff** buscando los secretos en texto plano, base64 y hex antes de aceptarlo | El diff es el único canal de salida que el diseño Gemelo deja sin cubrir, y es probable que un juez técnico pregunte por él primero. | Sin protección; tratarlo como salida que requiere desclasificación | P1 · h8 | 2026-11-21 |
| D4 | ¿Cómo se protege el token del gateway? | **Token por run**, más **expiración al terminar el run** y **tope propio en USD** | El token está en cada sandbox con salida a internet, así que podría filtrarse y usarse para drenar el crédito. | Solo el token por run (lo que ya dice el brief) | P2 · h8 | 2026-11-21 |
| D5 | ¿Qué corta el lane FIDES? | **Todo menos el gateway** | Si se corta el gateway, el agente muere y FIDES parecería romper la tarea por la razón equivocada. La detección mira el contenido de los resultados vía `PostToolUse`, no el comando. | Cortar toda la red | P2 · h10 | 2026-11-21 |
| D6 | ¿Cuándo dejamos de mantener dos providers? | **Criterio de corte en h16**: si E2B no pasa la suite de conformidad en h16, producción corre solo el Gemelo en E2B y los otros lanes quedan locales con replay | Mantener Docker y E2B a la par, más la desclasificación, es demasiado para P1 en 30 h. El corte acota el riesgo sin renunciar a E2B. | Mantener ambos providers siempre, pasando los mismos tests | P1 · h16 | 2026-11-21 |
| D7 | ¿Cómo se presenta el proyecto en el pitch? | **"Firewall" como gancho, corregido en la segunda frase**: *"Los firewalls de IA intentan detectar la filtración y se dejan engañar. Gemelo no detecta nada: separa al agente para que nunca tenga, al mismo tiempo, el secreto y la salida a internet."* | El jurado entiende "firewall" al tiro; la segunda frase aclara que el Gemelo no filtra, separa. | "Firewall de agentes" a secas; "Contención de agentes" | P5 · h27 | 2026-11-21 |

## Pendientes

Ninguna por ahora.
