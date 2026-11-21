# Entorno de desarrollo

Qué instalar y cómo dejar el proyecto corriendo en local, igual para todo el equipo.

## 1. Herramientas

| Herramienta | Versión | Para qué | Instalación |
|---|---|---|---|
| Git | 2.4x+ | Control de versiones | https://git-scm.com |
| Docker Desktop | 28+ | Sandboxes locales y servicios con `docker compose` | https://www.docker.com/products/docker-desktop |
| Node.js | 22.20+ | Web (Next.js) y CLI de OpenSpec | https://nodejs.org |
| pnpm | 9+ | Dependencias de la web | `npm install -g pnpm` |
| uv | 0.13+ | Python 3.12 y dependencias de la API | `pip install --user uv` o https://docs.astral.sh/uv |
| OpenSpec | 2.1+ | Specs y cambios del proyecto | `npm install -g @fission-ai/openspec@latest` |
| make | 4+ | Atajos del `Makefile` (opcional) | Windows: `winget install ezwinports.make` |

No hace falta instalar Python 3.12 a mano: `uv` lo descarga solo para el proyecto.

### Notas para Windows

- Si `uv` se instaló con `pip install --user`, agregar al `Path` de usuario la carpeta `%APPDATA%\Python\Python3XX\Scripts`. Revisar que la entrada no quede con espacios al inicio.
- Después de cambiar el `Path`, reiniciar la terminal (y el editor).
- Docker Desktop tiene que estar abierto para usar `docker` y correr los tests.
- El repo fuerza finales de línea LF (`.gitattributes`), porque los scripts se copian a contenedores Linux y con CRLF fallan (`bash\r: not found`). Si clonaste antes del commit que agregó `.gitattributes`, tu copia de trabajo puede seguir en CRLF. Con todo commiteado, corre una vez:

  ```bash
  git rm --cached -r . && git reset --hard
  ```

  Para revisar que no quede ningún archivo en CRLF: `git ls-files --eol | grep w/crlf` no debería mostrar nada.

## 2. Primer setup

```bash
git clone https://github.com/platanus-hack/platanus-hack-26-cl-team-13.git
cd platanus-hack-26-cl-team-13
git checkout dev

cp .env.example .env              # completar solo lo necesario; no commitear .env

cd services/api && uv sync        # crea .venv con Python 3.12 y las dependencias
cd ../..

pnpm --dir apps/web install       # dependencias de la web
```

## 3. Comandos del día a día

| Qué | Con make | Sin make |
|---|---|---|
| Imagen del sandbox | `make sandbox-image` | `docker build -t gemelo-sandbox:local sandbox` |
| Tests de la API | `make test` | `cd services/api && uv run pytest` |
| Levantar servicios | `make up` | `docker compose up --build` |
| Bajar servicios | `make down` | `docker compose down` |
| Web en desarrollo | — | `pnpm --dir apps/web dev` |

## 4. Flujo de trabajo

- Se trabaja en la rama `dev`. `main` solo recibe lo estable.
- Todo cambio pasa por OpenSpec antes que por código: `/openspec-propose` → revisión → `/openspec-apply-change` → `/openspec-archive-change`. Los cambios viven en `openspec/changes/`.
- Las decisiones del proyecto están en [`docs/DECISIONES.md`](DECISIONES.md).

## Pendiente

Estos pasos se agregan a medida que se implementan los cambios:

- Variables de `.env` para el gateway, E2B y canary tokens (`add-model-gateway`, `add-honeytoken-detection`).
- `make run TASK=... LANES=...`: correr una tarea completa en local.
