# Tasks

## 1. Plantilla del sandbox

- [x] 1.1 Reescribir `sandbox/Dockerfile` sobre Node 22 con Claude Code, git, Python 3.12 y los hooks; verificar que `claude --version`, `git --version` y `python --version` responden dentro de la imagen
- [x] 1.2 Agregar el target `make sandbox-image` y verificar que construye la imagen desde cero

## 2. Interfaz y fábrica

- [x] 2.1 Definir la interfaz `SandboxProvider` y los perfiles de red (`open`, `isolated(allowlist)`, `gateway_only`) en `providers/__init__.py`; verificar con un test que la fábrica devuelve el proveedor según `SANDBOX_PROVIDER` y falla con un valor inválido
- [x] 2.2 Agregar `SANDBOX_PROVIDER` y `E2B_API_KEY` a `.env.example` con comentarios; verificar que el archivo no contiene valores reales

## 3. Proveedor local

- [ ] 3.1 Agregar a `docker-compose.yml` las redes `egress` e `internal` (`internal: true`) y conectar el gateway a ambas; verificar con `docker network inspect` que `internal` no tiene salida
- [ ] 3.2 Implementar `providers/local.py` (crear, ejecutar con streaming, leer archivos, `git diff`, destruir) y verificar con los tests de ciclo de vida
- [ ] 3.3 Implementar el proxy de allowlist en la red `internal` y verificar que un dominio permitido sale y uno no permitido falla
- [ ] 3.4 Implementar el corte en caliente (`set_network` a `gateway_only`) y verificar que el atacante deja de responder, el gateway sigue respondiendo y los archivos se conservan
- [ ] 3.5 Spike F0: desde un contenedor aislado, `curl` al atacante falla y el gateway responde; dejar el resultado anotado en `design.md`

## 4. Suite de conformidad

- [ ] 4.1 Escribir en `services/api/tests/` un test por escenario de `specs/sandbox-provider/spec.md`, parametrizado por proveedor; verificar que `make test` los corre contra `local` y pasan
- [ ] 4.2 Agregar el test de limpieza: una corrida que lanza una excepción no deja contenedores con su etiqueta; verificar con `docker ps -a --filter label=...`

## 5. Proveedor E2B

- [ ] 5.1 Construir la plantilla E2B a partir del mismo Dockerfile y verificar que un sandbox nuevo pasa el test de herramientas disponibles
- [ ] 5.2 Implementar `providers/e2b.py` con `denyOut`/`allowOut` y cambio de reglas en caliente; verificar con `SANDBOX_PROVIDER=e2b make test`
- [ ] 5.3 Manejar el error de cuota de E2B (límite de sandboxes simultáneos) con una excepción explícita y verificarlo con un test que simula la respuesta de cuota

## 6. Integración

- [ ] 6.1 En h16, correr la suite completa con ambos proveedores y aplicar el criterio D6: si E2B falla, dejar solo el carril Gemelo en E2B y anotar el resultado en `docs/DECISIONES.md`

## Workflow follow-up

- Archivar el cambio cuando ambas suites pasen o cuando se aplique el corte de D6.
