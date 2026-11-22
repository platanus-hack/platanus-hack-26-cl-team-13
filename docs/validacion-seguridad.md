# Validación de seguridad de AIgis

Valida que el carril `gemelo` pueda completar `mask-keys` y que el gemelo bajo mantenga los datos del pool B dentro de los límites previstos. Usa un entorno de prueba, el gateway simulado y secretos desechables. Registra el commit, el proveedor y los identificadores de las imágenes para poder repetir la validación.

## 1. Controles de aplicación

Desde la raíz del repo, entra a `services/api` y ejecuta estas comprobaciones con Python 3.12 y las dependencias de desarrollo. En Windows, si ya tienes el entorno instalado, puedes sustituir `uv run pytest` por `.\.venv\Scripts\python.exe -m pytest`.

```text
cd services/api
uv run pytest -q tests/test_scanner.py tests/test_gateway.py tests/test_providers.py tests/test_run_flow.py::test_hook_rejects_foreign_token tests/test_run_flow.py::test_api_token_protects_reads
```

| Control | Criterio de aprobación |
| --- | --- |
| Escáner de secretos | Detecta y redacta los valores sintéticos en los formatos cubiertos por la suite. Acepta el diff limpio del control positivo. |
| Gateway | Rechaza tokens ausentes, vencidos y revocados. Las solicitudes válidas se contabilizan en su corrida y respetan los topes. |
| API y hooks | Los recursos protegidos requieren el token configurado. El hook rechaza un token de otra caja. |
| Perfiles de red | La configuración distingue red abierta, red aislada con destinos permitidos y acceso exclusivo al gateway. |

## 2. Conformidad del proveedor Docker

Desde la raíz, con Docker activo, construye las imágenes del sandbox y del proxy con `make sandbox-image`. Luego ejecuta desde `services/api` el siguiente comando. La suite usa un gateway simulado en el puerto `8787` y destinos públicos de referencia para controles de conectividad.

```text
uv run pytest -q -m docker tests/test_docker_provider.py
```

| Control | Criterio de aprobación |
| --- | --- |
| Salida del gemelo bajo | El gateway y el destino permitido responden. Los destinos fuera de la lista y la resolución DNS externa quedan bloqueados. |
| Separación entre cajas | El servicio de prueba responde dentro de su propia caja y queda inaccesible desde las otras cajas evaluadas. |
| Corte de red | La caja abierta alcanza el destino de control antes del corte. Después del corte conserva el archivo de prueba y el acceso al gateway, y pierde acceso al destino público. |
| Permisos y limpieza | La imagen carece de las credenciales de proveedor comprobadas por la suite. El usuario del agente tiene acceso de solo lectura al traspaso probado y a la configuración administrada. La caja desaparece del listado tras su destrucción. |

El proveedor `fake` sirve para comprobar decisiones de la aplicación. La cobertura del aislamiento depende del proveedor que ejecuta la prueba. Para una demo sobre E2B, verifica el proveedor desplegado con `uv run pytest -q -m e2b tests/test_e2b_provider.py` y su plantilla de prueba.

## 3. Validación del resultado de la demo

1. Levanta el orquestador en local con `AIGIS_AGENT=scripted` y `AIGIS_GATEWAY_STUB=true` según el [README de la API](../services/api/README.md). Crea una corrida con `POST /runs` y el cuerpo `{"task_id":"mask-keys"}`. Usa `GET /runs/{run_id}` para guardar el resultado de `lanes.gemelo.result` y `GET /runs/{run_id}/events` para revisar la secuencia.
2. Confirma que el cambio legítimo termina con `test.result.passed=true`, `scan.result.clean=true`, `verdict=delivered` y `delivered=true`. Revisa el diff publicado en `GET /runs/{run_id}/lanes/gemelo/diff` con los valores sintéticos de la corrida.
3. Para comprobar el control de entrega con los fixtures del repo, ejecuta desde `services/api` el comando de abajo en Linux o WSL. Los fixtures dependen de utilidades de Bash. Espera un veredicto `rejected_leak`, `delivered=false` y que el diff persistido siga redactado tras simular un reinicio. En el flujo de la API, `scan.result.clean=false` identifica el escaneo que bloqueó la entrega.
4. Cuando haya una detección de red, revisa su atribución por corrida, caja y pool. Un honeytoken del pool A en el gemelo alto es el resultado esperado de ese control. Cualquier valor del pool B observado fuera del límite previsto de la corrida es un fallo de confidencialidad. Revisa también `leaked` en el resultado de `gemelo`, incluso si la tarea o el escaneo del diff pasaron.

```text
uv run pytest -q tests/test_run_flow.py::test_diff_with_hidden_secret_is_rejected tests/test_run_flow.py::test_diff_stays_redacted_after_restart
```

## Decisión para la demo

Anota por control el resultado (`aprobado`, `fallido` o `pendiente`), el ID de corrida cuando corresponda y la evidencia redactada. Un `skip`, un timeout o un control positivo fallido deja la comprobación pendiente. Bloquea la demo de aislamiento si falla la conformidad del proveedor desplegado, aparece un valor del pool B fuera de su límite o se entrega un diff que el escáner marcó. El resultado respalda los controles ejecutados para ese commit y ese entorno.
