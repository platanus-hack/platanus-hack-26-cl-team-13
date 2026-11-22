# Sink del atacante (solo biblioteca estándar). Contexto: services/attacker.
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY sink.py .
COPY bucket ./bucket
RUN useradd --uid 10002 attacker
USER attacker
ENV PYTHONUNBUFFERED=1
EXPOSE 9000
CMD ["python", "sink.py"]
