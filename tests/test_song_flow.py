"""Song mode end to end in MOCK mode, plus the controller's caps and fallbacks. Invented text only."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import config, song_controller
from app.backends import mock
from app.limits import Limits, limits
from app.main import app
from app.song import Identification, parse_lrc
from app.song_controller import SongController

FAST = dict(MOCK_WORD_S=0.01, MOCK_GAP_S=0.03)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    limits._buckets.clear()
    monkeypatch.setitem(Limits.KINDS, "song", (1, 0.05))          # the real spacing is 20 s; see the controller tests
    monkeypatch.setattr(config, "LIMIT_SONG", (1, 0.05))
    monkeypatch.setattr(song_controller, "TICK_S", 0.01)
    for k, v in FAST.items():
        monkeypatch.setattr(mock, k, v)
    yield
    limits._buckets.clear()


def _pump(ws, want, limit=400):
    """Keep the mock singer 'hearing' audio while collecting messages until `want(msg)` is true."""
    seen = []
    for _ in range(limit):
        ws.send_bytes(b"\x02" + b"\x00\x00" * 1920)
        m = ws.receive_json()
        seen.append(m)
        if want(m):
            return m, seen
    raise AssertionError(f"not seen in {limit} messages; types: {[x['type'] for x in seen][-10:]}")


def test_song_mode_refused_when_server_flag_off(monkeypatch):
    monkeypatch.setattr(config, "SONG_MODE", False)
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        assert ws.receive_json()["song_mode"] is False
        ws.send_json({"type": "song_start"})
        m = ws.receive_json()
        assert m["type"] == "song" and m["state"] == "off"


def test_song_mode_needs_lyrics_first(monkeypatch):
    monkeypatch.setattr(config, "SONG_MODE", True)
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        assert ws.receive_json()["song_mode"] is True
        ws.send_json({"type": "song_start"})
        m = ws.receive_json()
        assert m["state"] == "off" and "Lyrics" in m["detail"]


def test_mock_full_flow_found_then_lines_advance(monkeypatch):
    monkeypatch.setattr(config, "SONG_MODE", True)
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        ws.receive_json()
        ws.send_json({"type": "lyrics_start"})
        assert _pump(ws, lambda m: m["type"] == "lyrics_state")[0]["on"] is True
        ws.send_json({"type": "song_start"})
        listening, _ = _pump(ws, lambda m: m["type"] == "song")
        assert listening["state"] == "listening"
        found, _ = _pump(ws, lambda m: m["type"] == "song" and m["state"] == "found")
        assert found["title"] == mock.MOCK_SONG_TITLE and found["credit"] == "lyrics via LRCLIB"
        first, _ = _pump(ws, lambda m: m["type"] == "song_line")
        later, _ = _pump(ws, lambda m: m["type"] == "song_line" and m["idx"] != first["idx"])
        assert later["cur"] in mock.MOCK_SONG_LINES and first["cur"] in mock.MOCK_SONG_LINES
        assert "next" in later
        ws.send_json({"type": "song_stop"})
        ws.send_json({"type": "lyrics_stop"})
        _pump(ws, lambda m: m["type"] == "lyrics_state" and m["on"] is False)


def test_live_lyrics_keep_flowing_alongside_song_lines(monkeypatch):
    monkeypatch.setattr(config, "SONG_MODE", True)
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        ws.receive_json()
        ws.send_json({"type": "lyrics_start"})
        _pump(ws, lambda m: m["type"] == "lyrics_state")
        ws.send_json({"type": "song_start"})
        _, seen = _pump(ws, lambda m: m["type"] == "song_line")
        assert any(m["type"] == "lyric" for m in seen)      # plain lyrics were never interrupted (fallback is client-side)


# ---------------------------------------------------------------- controller, driven directly

class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Ident:
    name = "fake"

    def __init__(self, result):
        self.result, self.calls = result, 0

    async def identify(self, heard):
        self.calls += 1
        return self.result


class Source:
    name = "fake"

    def __init__(self, lrc):
        self.lrc, self.calls = lrc, 0

    async def find(self, title, artist):
        self.calls += 1
        return self.lrc


LRC = parse_lrc("[00:02.00] paper boats on a copper river\n[00:06.00] we were counting the lanterns twice\n"
                "[00:10.00] hold the evening in your pocket\n")
HEARD = ["paper boats on a copper river", "we were counting the lanterns twice"]


def _controller(ident, source, clock):
    sent = []

    async def send(**m):
        sent.append(m)
    return SongController(send, "1.2.3.4", live=False, clock=clock, identifier=ident, source=source), sent


def _hear(sc, lines, clock):
    for ln in lines:
        sc.feed({"type": "speechComplete", "transcript": ln})
        clock.t += 1.0


async def _run_for(sc, seconds=0.2):
    await sc.start()
    await asyncio.sleep(seconds)
    await sc.stop()


def test_controller_not_recognised_falls_back_after_max_attempts():
    clk = FakeClock()
    ident, src = Ident(None), Source(LRC)
    sc, sent = _controller(ident, src, clk)

    async def go():
        await sc.start()
        for _ in range(config.SONG_MAX_ATTEMPTS + 2):
            clk.t += 21                         # past the 20 s spacing each round
            limits._buckets.clear()             # the per-IP bucket refills in real time; fake clock can't
            _hear(sc, HEARD, clk)               # heard after the jump, so the 15 s buffer still holds it
            await asyncio.sleep(0.08)
        await sc.stop()
    asyncio.run(go())
    assert ident.calls == config.SONG_MAX_ATTEMPTS           # capped
    assert src.calls == 0                                    # nothing to look up
    assert sent[-1] == {"type": "song", "state": "none", "reason": "nomatch"}
    assert sc.tracker is None


def test_controller_one_try_per_20s_while_unmatched(monkeypatch):
    monkeypatch.setattr(config, "LIMIT_SONG", (1, 20.0))      # the real spacing (the fixture shortens it)
    clk = FakeClock()
    ident, src = Ident(None), Source(LRC)
    sc, sent = _controller(ident, src, clk)

    async def go():
        _hear(sc, HEARD, clk)
        await sc.start()
        await asyncio.sleep(0.15)                # many ticks, clock frozen after the first try
        clk.t += 10
        await asyncio.sleep(0.15)                # only 10 s later: no second try
        await sc.stop()
    asyncio.run(go())
    assert ident.calls == 1


def test_controller_rejects_wrong_song_by_verification():
    clk = FakeClock()
    wrong = parse_lrc("[00:02.00] completely different words here today\n[00:06.00] nothing alike at all really\n")
    ident, src = Ident(Identification("Other", "Someone", 0.9)), Source(wrong)
    sc, sent = _controller(ident, src, clk)

    async def go():
        _hear(sc, HEARD, clk)
        await _run_for(sc)
    asyncio.run(go())
    assert ident.calls == 1 and src.calls == 1
    assert not [m for m in sent if m.get("state") == "found"]
    assert sc.tracker is None


def test_controller_lookup_failure_is_not_recognised_and_cached():
    clk = FakeClock()
    ident, src = Ident(Identification("Placeholder Song", "Nobody", 0.9)), Source(None)
    sc, sent = _controller(ident, src, clk)

    async def go():
        _hear(sc, HEARD, clk)
        await _run_for(sc)
    asyncio.run(go())
    assert src.calls == 1 and sc.cache[("placeholder song", "nobody")] is None
    assert not [m for m in sent if m.get("state") == "found"]


def test_controller_found_then_lost_after_silence():
    clk = FakeClock()
    ident, src = Ident(Identification("Placeholder Song", "Nobody", 0.9)), Source(LRC)
    sc, sent = _controller(ident, src, clk)

    async def go():
        _hear(sc, HEARD, clk)
        await sc.start()
        await asyncio.sleep(0.15)
        assert sc.tracker and sc.tracker.locked
        clk.t += 16                              # no confident match for >15 s
        await asyncio.sleep(0.15)
        await sc.stop()
    asyncio.run(go())
    states = [m["state"] for m in sent if m["type"] == "song"]
    assert states[:2] == ["listening", "found"] and "lost" in states
    assert any(m["type"] == "song_line" for m in sent)


def test_controller_budget_exhausted_gives_up(monkeypatch):
    clk = FakeClock()
    ident, src = Ident(None), Source(LRC)
    sent = []

    async def send(**m):
        sent.append(m)
    sc = SongController(send, "1.2.3.4", live=True, clock=clk, identifier=ident, source=src)
    monkeypatch.setattr(limits, "can_spend", lambda usd: False)

    async def go():
        _hear(sc, HEARD, clk)
        await _run_for(sc)
    asyncio.run(go())
    assert ident.calls == 0
    assert sent[-1]["state"] == "none" and sent[-1]["reason"] == "budget"
