.PHONY: up down test test-docker eval sandbox-image api gateway export-run

SANDBOX_IMAGE ?= aigis-sandbox:local
PROXY_IMAGE ?= aigis-proxy:dev

# Imágenes del provider local: sandbox (Claude Code + hooks) y proxy de salida
sandbox-image:
	docker build -t $(SANDBOX_IMAGE) sandbox
	docker build -t $(PROXY_IMAGE) egress_proxy

up:
	docker compose up --build

down:
	docker compose down

# Orquestador en local. AIGIS_SANDBOX_PROVIDER=local usa Docker; fake no aísla nada.
api:
	cd services/api && uv run uvicorn aigis.app:app --host 0.0.0.0 --port 8000

# Gateway del modelo en :8787 (lee GATEWAY_* del entorno o de .env)
gateway:
	cd services/api && uv run uvicorn aigis.gateway.app:app --port 8787 --no-access-log

test:
	cd services/api && uv run pytest

test-docker: sandbox-image
	cd services/api && uv run pytest -m docker

eval:
	python eval/run_eval.py

# Exporta una corrida terminada a apps/web/public/replays/ para reproducirla sin API.
# Uso: make export-run RUN=<run_id> [WAIT=2m] [ID=nombre] [TITLE="..."] [TEST=1]
export-run:
	@test -n "$(RUN)" || (echo "falta RUN=<run_id>" && exit 2)
	cd apps/web && node scripts/export-run.mjs $(RUN) \
		$(if $(WAIT),--wait $(WAIT)) $(if $(ID),--id $(ID)) $(if $(TITLE),--title "$(TITLE)") $(if $(TEST),--test)
