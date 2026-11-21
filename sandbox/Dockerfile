# Plantilla del sandbox donde corre el agente (local con Docker; E2B parte del mismo archivo).
# Contiene: Node 22, Claude Code, git, Python 3.12, pytest, curl y los hooks del agente.
# No contiene ninguna API key ni credencial del orquestador: secretos y tokens se copian al crear cada caja.
# Construir: make sandbox-image  (tag gemelo-sandbox:local)

# Una sola etapa: E2B construye plantillas desde Dockerfile pero no admite multi-stage
# (docs.e2b.dev/template/base-image, "Multi-stage Dockerfiles are not supported").
# Node 22 se instala desde el tarball oficial, verificado contra SHASUMS256.txt.
FROM python:3.12-slim-bookworm

ARG CLAUDE_CODE_VERSION=2.1.330
ARG NODE_VERSION=22.20.0

# procps: el orquestador mata los procesos del agente al cortar por tiempo (pkill)
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates procps jq xz-utils \
 && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$(dpkg --print-architecture)" in amd64) arch=x64 ;; arm64) arch=arm64 ;; *) exit 1 ;; esac; \
    file="node-v${NODE_VERSION}-linux-${arch}.tar.xz"; \
    cd /tmp; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${file}"; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" | grep " ${file}\$" | sha256sum -c -; \
    tar -xJf "${file}" -C /usr/local --strip-components=1 --no-same-owner; \
    rm "${file}"; \
    node --version; npm --version

RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
 && npm cache clean --force

# pytest preinstalado: los tests de la tarea corren dentro del sandbox con la red cortada
ARG PYTEST_VERSION=9.2.0
RUN pip install --no-cache-dir "pytest==${PYTEST_VERSION}"

# Claude Code no debe hablar con nada salvo el gateway
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    DISABLE_AUTOUPDATER=1 \
    PYTHONDONTWRITEBYTECODE=1

# Usuario sin privilegios: el agente no puede tocar la red ni el sistema.
# uid fijo 1001: el provider local copia archivos con ese dueño.
# /handoff: traspaso bajo -> alto, de root y solo lectura para el agente.
RUN useradd --create-home --uid 1001 --shell /bin/bash agent \
 && mkdir -p /workspace /handoff /etc/claude-code \
 && chown agent:agent /workspace \
 && chmod 755 /handoff

# Hooks y agente con guion: de root y solo lectura para el agente
COPY hooks/ /opt/gemelo/hooks/
COPY scripted_agent.py /opt/gemelo/scripted_agent.py
# Política administrada: el agente no puede desactivar los hooks desde su ~/.claude
COPY settings.json /etc/claude-code/managed-settings.json
RUN chmod -R a+rX,go-w /opt/gemelo /etc/claude-code

USER agent
WORKDIR /workspace
RUN git config --global user.name "agent" \
 && git config --global user.email "agent@sandbox.local" \
 && git config --global init.defaultBranch main

CMD ["sleep", "infinity"]
