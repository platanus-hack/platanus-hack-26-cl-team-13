.PHONY: up down test test-docker eval sandbox-image api gateway

SANDBOX_IMAGE ?= gemelo-sandbox:local
PROXY_IMAGE ?= gemelo-proxy:dev

# Imágenes del provider local: sandbox (Claude Code + hooks) y proxy de salida
sandbox-image:
	docker build -t $(SANDBOX_IMAGE) sandbox
	docker build -t $(PROXY_IMAGE) egress_proxy

up:
	docker compose up --build

down:
	docker compose down

# Orquestador en local. GEMELO_SANDBOX_PROVIDER=local usa Docker; fake no aísla nada.
api:
	cd services/api && uv run uvicorn gemelo.app:app --host 0.0.0.0 --port 8000

# Gateway del modelo en :8787 (lee GATEWAY_* del entorno o de .env)
gateway:
	cd services/api && uv run uvicorn gemelo.gateway.app:app --port 8787 --no-access-log

test:
	cd services/api && uv run pytest

test-docker: sandbox-image
	cd services/api && uv run pytest -m docker

eval:
	python eval/run_eval.py
