from app.limits import Limits, TokenBucket


def test_bucket_burst_then_blocks():
    b = TokenBucket(2, 60)
    assert b.take() and b.take() and not b.take()


def test_budget_blocks_when_spent():
    lim = Limits(daily_budget=0.02)
    assert lim.can_spend(0.01)
    lim.charge("image", 0.015)
    assert not lim.can_spend(0.01)
    assert lim.status()["calls"]["image"] == 1


def test_perform_time_per_ip():
    lim = Limits(perform_seconds=180)
    assert lim.perform_remaining("1.2.3.4") == 180
    lim.start_perform("1.2.3.4")
    assert 179 < lim.perform_remaining("1.2.3.4") <= 180
    assert lim.perform_remaining("5.6.7.8") == 180


def test_per_ip_buckets_are_separate():
    lim = Limits()
    for _ in range(6):
        assert lim.allow("a", "cue")
    assert not lim.allow("a", "cue")
    assert lim.allow("b", "cue")


def test_client_ip_ignores_spoofed_first_forwarded_entry():
    from app.main import client_ip
    assert client_ip({"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, None) == "1.2.3.4"
    assert client_ip({"true-client-ip": "9.9.9.9", "x-forwarded-for": "6.6.6.6"}, None) == "9.9.9.9"
