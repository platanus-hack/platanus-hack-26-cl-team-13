from app.phones import normalize_phone


def test_keeps_leading_plus_and_digits():
    assert normalize_phone("+56 9 8765-4321") == "+56987654321"


def test_drops_symbols():
    assert normalize_phone("  (2) 123-4567 ext. 8 ") == "212345678"


def test_plus_only_at_start():
    assert normalize_phone("56+56") == "5656"


def test_no_digits():
    assert normalize_phone("-- ()") == ""
