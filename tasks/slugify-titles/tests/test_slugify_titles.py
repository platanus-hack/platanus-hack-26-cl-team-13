from app.slug import slugify


def test_accents():
    assert slugify("¿Qué es la Inyección de Prompts?") == "que-es-la-inyeccion-de-prompts"


def test_enie_and_symbols():
    assert slugify("  Año 2026 -- ¡Niños & niñas!  ") == "ano-2026-ninos-ninas"


def test_max_len_whole_words():
    s = slugify("palabra " * 20)
    assert len(s) <= 60 and not s.endswith("-") and s.split("-") == ["palabra"] * 7
