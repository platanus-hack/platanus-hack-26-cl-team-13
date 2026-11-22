from app.signature import verify_signature


def test_importa():
    assert callable(verify_signature)
