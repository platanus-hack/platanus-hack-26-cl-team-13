"""Costo estimado de una llamada a partir del `usage` que devuelve la API.

Precios en USD por millón de tokens: entrada, salida, escritura de caché (5 min) y lectura
de caché. Fuente: tabla de modelos de la skill claude-api de Claude Code (caché del
2026-11-03), evidencia secundaria. POR VERIFICAR contra https://platform.claude.com/docs/en/about-claude/pricing
antes de la demo; se corrigen sin desplegar con GATEWAY_PRICES_JSON.

Escritura de caché a 1,25x la entrada (5 min) y 2x (1 h); lectura según tabla. Haiku 5.5
cobra 5x sobre 100K tokens de prompt (misma fuente).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MTOK = 1_000_000
OVERHEAD_TOKENS = 1_000


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float
    cache_read: float
    long_threshold: int = 0  # tokens de prompt sobre los que aplica long_mult (0 = nunca)
    long_mult: float = 1.0


# claude-haiku-5-5 y claude-sonnet-5-5: modelo y fecha de la cifra en el docstring del módulo
DEFAULT_PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(0.10, 0.50, 0.125, 0.01, long_threshold=100_000, long_mult=5.0),
    "claude-sonnet-5-5": Price(2.00, 10.00, 2.50, 0.10),
    "claude-opus-5-5": Price(4.00, 20.00, 5.00, 0.20),
}
# Modelo desconocido: se cobra como el más caro conocido, para que el tope nunca se subestime
FALLBACK = Price(10.00, 50.00, 12.50, 1.00)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_1h_input_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens

    def merge(self, raw: dict | None) -> None:
        """Toma los campos presentes en un objeto `usage` de la API (los de message_delta
        son acumulados, así que se sobrescriben, no se suman)."""
        if not raw:
            return
        for f in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            v = raw.get(f)
            if isinstance(v, int) and v >= 0:
                setattr(self, f, v)
        cc = raw.get("cache_creation")
        if isinstance(cc, dict):
            one_h = cc.get("ephemeral_1h_input_tokens")
            if isinstance(one_h, int) and one_h >= 0:
                self.cache_creation_1h_input_tokens = one_h


class PriceTable:
    def __init__(self, override_json: str = "") -> None:
        self.prices = dict(DEFAULT_PRICES)
        if override_json.strip():
            for model, vals in json.loads(override_json).items():
                self.prices[model] = Price(*[float(v) for v in vals[:4]])

    def price(self, model: str) -> Price:
        return self.prices.get(model, FALLBACK)

    def cost(self, model: str, u: Usage) -> float:
        p = self.price(model)
        mult = p.long_mult if p.long_threshold and u.prompt_tokens > p.long_threshold else 1.0
        cw_1h = min(u.cache_creation_1h_input_tokens, u.cache_creation_input_tokens)
        cw_5m = u.cache_creation_input_tokens - cw_1h
        usd = (u.input_tokens * p.input
               + u.output_tokens * p.output
               + cw_5m * p.cache_write
               + cw_1h * p.input * 2.0
               + u.cache_read_input_tokens * p.cache_read) / MTOK
        return usd * mult

    def worst_case_input(self, model: str, body_bytes: int) -> float:
        """Cota alta del costo de entrada: ~3 bytes por token, cobrado como escritura de caché
        a 1 h (lo más caro posible) y con el multiplicador de contexto largo. Suma un margen
        fijo por el prompt de sistema que la API agrega al usar herramientas."""
        p = self.price(model)
        tokens = body_bytes // 3 + OVERHEAD_TOKENS
        mult = p.long_mult if p.long_threshold and tokens > p.long_threshold else 1.0
        return tokens * max(p.input * 2.0, p.cache_write) * mult / MTOK

    def output_per_token(self, model: str, body_bytes: int) -> float:
        p = self.price(model)
        tokens = body_bytes // 3 + OVERHEAD_TOKENS
        mult = p.long_mult if p.long_threshold and tokens > p.long_threshold else 1.0
        return p.output * mult / MTOK
