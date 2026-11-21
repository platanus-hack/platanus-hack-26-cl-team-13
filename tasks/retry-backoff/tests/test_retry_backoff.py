from app.retry import backoff_delays


def test_default():
    assert backoff_delays(5) == [0.5, 1.0, 2.0, 4.0, 8.0]


def test_cap():
    assert backoff_delays(7, base=1, factor=3, max_delay=10) == [1, 3, 9, 10, 10, 10, 10]


def test_empty():
    assert backoff_delays(0) == [] and backoff_delays(-2) == []
