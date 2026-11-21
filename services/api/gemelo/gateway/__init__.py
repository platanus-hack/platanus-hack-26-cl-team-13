"""Gateway del modelo: proxy compatible con la API de Anthropic para los Claude Code de las cajas.

Las cajas reciben `ANTHROPIC_BASE_URL` apuntando aquí y un token por corrida (o por caja)
en `ANTHROPIC_AUTH_TOKEN`. La API key real vive solo en este proceso. Cada token expira,
se puede revocar y tiene su propio tope en USD (decisión D4).

Se levanta con `uvicorn gemelo.gateway.app:app`. Contrato en services/api/README.md.
"""
