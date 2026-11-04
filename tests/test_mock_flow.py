from fastapi.testclient import TestClient

from app.main import app


def _until(ws, kind, limit=10):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == kind:
            return m
    raise AssertionError(f"no {kind}")


def test_text_cue_produces_scene_in_mock_mode():
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["mode"] == "mock"
        ws.send_json({"type": "text_cue", "text": "Make it feel like a rainy city at 3am"})
        scene = _until(ws, "scene")
        assert scene["scene"]["nearest_backdrop"] == "rain_city"


def test_push_to_talk_mock_roundtrip():
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        ws.receive_json()
        ws.send_json({"type": "ptt_start"})
        ws.send_bytes(b"\x01" + b"\x00\x00" * 1920)
        ws.send_json({"type": "ptt_end"})
        final = None
        for _ in range(10):
            m = ws.receive_json()
            if m["type"] == "transcript" and m["final"]:
                final = m
            if m["type"] == "scene" and m["source"] != "instant":
                break
        assert final and final["text"]


def test_health_reports_mock_and_budget():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["mode"] == "mock" and h["budget"]["budget_usd"] > 0


def test_lyrics_stream_mock():
    with TestClient(app) as c, c.websocket_connect("/ws/stage") as ws:
        ws.receive_json()
        ws.send_json({"type": "lyrics_start"})
        assert _until(ws, "lyrics_state")["on"] is True
        words = []
        for _ in range(12):
            ws.send_bytes(b"\x02" + b"\x00\x00" * 1920)
            m = ws.receive_json()
            if m["type"] == "lyric":
                words.append(m["text"])
            if len(words) >= 2:
                break
        assert words and words[-1].startswith(words[0].split()[0])
        ws.send_json({"type": "lyrics_stop"})
        assert _until(ws, "lyrics_state")["on"] is False
