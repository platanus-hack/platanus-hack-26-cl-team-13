from app.dsn import parse_dsn


def test_full():
    d = parse_dsn("postgresql://app:s%40cret@db.internal:6543/inventario")
    assert d == {"scheme": "postgresql", "user": "app", "password": "s@cret",
                 "host": "db.internal", "port": 6543, "database": "inventario"}


def test_default_port():
    assert parse_dsn("postgres://u@h/x")["port"] == 5432


def test_missing_parts():
    d = parse_dsn("redis://cache")
    assert d["user"] is None and d["password"] is None and d["database"] is None and d["port"] is None
