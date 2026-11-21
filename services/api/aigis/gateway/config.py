"""Configuración del gateway, variables con prefijo GATEWAY_.

Los secretos (`GATEWAY_UPSTREAM_URL` cuando lleva el token de la hackatón en la ruta,
`GATEWAY_UPSTREAM_API_KEY`, `GATEWAY_ADMIN_TOKEN`) solo se leen del entorno y nunca se
escriben en logs, respuestas ni eventos.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    # Base del upstream compatible con Anthropic. Puede ser https://api.anthropic.com o el
    # proxy de la hackatón (https://llm.hack.platan.us/t/<token>/anthropic), que igual exige
    # la key del proveedor en x-api-key.
    upstream_url: SecretStr = SecretStr("https://api.anthropic.com")
    upstream_api_key: SecretStr = SecretStr("")

    # Token de administración que usa el orquestador. Vacío = rutas /admin deshabilitadas.
    admin_token: SecretStr = SecretStr("")

    # Modelo fijado por el gateway. Un pedido con un modelo de allowed_models se respeta;
    # cualquier otro se reescribe a `model`.
    model: str = "claude-haiku-5-5"
    allowed_models: str = ""

    # Límites de emisión de tokens
    default_budget_usd: float = 2.50
    max_budget_usd: float = 20.0
    default_ttl_s: int = 1800
    max_ttl_s: int = 4 * 3600
    # Llamadas al modelo por token (0 = sin tope). Respaldo del tope de pasos del agente.
    max_requests: int = 400
    # Si el saldo no alcanza para esta salida mínima, la llamada se rechaza con 402
    min_output_tokens: int = 256

    # Precios por MTok como JSON {"modelo": [in, out, cache_write, cache_read]} para
    # corregir la tabla de pricing.py sin desplegar código.
    prices_json: str = ""

    upstream_timeout_s: float = 600.0
    # Cuánto se guardan los tokens terminados para consultar su uso
    retain_s: int = 24 * 3600

    @property
    def allowed_model_set(self) -> set[str]:
        return {m.strip() for m in self.allowed_models.split(",") if m.strip()} | {self.model}

    @property
    def upstream_base(self) -> str:
        return self.upstream_url.get_secret_value().rstrip("/")


@lru_cache
def get_gateway_settings() -> GatewaySettings:
    return GatewaySettings()
