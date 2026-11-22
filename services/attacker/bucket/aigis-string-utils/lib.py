"""Utilidades de texto de aigis-string-utils."""


def digits_only(text: str) -> str:
    """Devuelve solo los digitos de un texto."""
    return "".join(ch for ch in text if ch.isdigit())
