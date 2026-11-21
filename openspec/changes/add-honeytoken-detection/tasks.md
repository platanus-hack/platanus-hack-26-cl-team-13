# Tasks

## 1. Pools de valores

- [ ] 1.1 Implementar en `honeytokens.py` los generadores por tipo de secreto (AWS, GitHub, llave de API genérica) con semilla; verificar con tests de formato por tipo
- [ ] 1.2 Generar y versionar el pool de secretos sintéticos; verificar con un test que no intersecta con los honeytokens generados
- [ ] 1.3 Implementar la asignación única de honeytokens por corrida, carril y gemelo; verificar el escenario de dos carriles en la misma corrida
- [ ] 1.4 Cargar los canary tokens desde `secrets/canaries.json`, agregarlo a `.gitignore` y agregar `CANARY_WEBHOOK_SECRET` a `.env.example`; verificar con un test que ningún canary cargado aparece en archivos versionados
- [ ] 1.5 Generar los 30–50 canary tokens AWS en canarytokens.org y guardarlos en `secrets/canaries.json`; verificar que el archivo no aparece en `git status`

## 2. Servidor atacante

- [ ] 2.1 Implementar en `services/attacker/sink.py` el registro de toda petición (ruta, query, headers, cuerpo, marca de tiempo) y su entrega a la API; verificar el escenario de exfiltración por POST
- [ ] 2.2 Agregar el servicio atacante a `docker-compose.yml` en la red `egress`; verificar que un contenedor abierto lo alcanza y uno aislado no

## 3. Decodificación y detección

- [ ] 3.1 Implementar el módulo de variantes (claro, base64 con alineaciones y padding, hex) compartido con el escaneo del diff; verificar con tests por formato
- [ ] 3.2 Implementar la detección en claro, base64 y hex en cualquier parte de la petición, incluidos envoltorios codificados; verificar los escenarios de honeytoken en base64 y secreto en hex
- [ ] 3.3 Implementar la detección de fragmentos por corrida con largo mínimo de 4; verificar el escenario de llave en tres peticiones y un caso que no debe detectarse
- [ ] 3.4 Implementar la atribución a carril, gemelo y paso, y la clasificación honeytoken o secreto verdadero, con su evento; verificar los escenarios de alarma del gemelo alto y carril sin defensa

## 4. Alertas de canary

- [ ] 4.1 Implementar el webhook de canarytokens validado con `CANARY_WEBHOOK_SECRET` y su simulación local; verificar los escenarios de webhook válido y sin secreto
- [ ] 4.2 Implementar el disparo de la alerta por el atacante con una llamada AWS de solo lectura; verificar con un test que la llamada se intenta y se registra (sin red real)
- [ ] 4.3 Grabar una alerta de canary real como respaldo para la demo; verificar que queda disponible para la web

## 5. Integración

- [ ] 5.1 Con el agente con guion, correr una exfiltración en base64 desde un sandbox abierto y verificar que se emite la detección con carril, gemelo y paso correctos

## Workflow follow-up

- Archivar el cambio cuando todas las tareas estén completas.
