from app.keys import mask_key


def test_long_key_keeps_last_four():
    assert mask_key("sk_live_abcdefgh1234") == "*" * 16 + "1234"


def test_short_key_fully_masked():
    assert mask_key("abc123") == "******"


def test_empty():
    assert mask_key("") == ""
