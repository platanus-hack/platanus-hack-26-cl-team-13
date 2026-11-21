from app.ratelimit import TokenBucket


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_burst_then_refill():
    c = Clock()
    b = TokenBucket(rate=2, capacity=3, clock=c)
    assert [b.allow() for _ in range(4)] == [True, True, True, False]
    c.t = 0.5
    assert b.allow() and not b.allow()


def test_capacity_cap():
    c = Clock()
    b = TokenBucket(rate=10, capacity=2, clock=c)
    c.t = 100
    assert b.allow(2) and not b.allow()


def test_no_partial_spend():
    c = Clock()
    b = TokenBucket(rate=1, capacity=1, clock=c)
    assert not b.allow(2) and b.allow(1)
