"""Song mode logic. All text here is invented; no real lyrics anywhere in the repo."""

import json

from app.song import (SongTracker, TranscriptBuffer, norm, parse_identification, parse_lrc,
                      similarity, verify_match)

# An invented song with a repeated chorus, to test drift and chorus handling.
LRC = """[ti:Placeholder Song]
[ar:Nobody]
[00:04.00] paper boats on a copper river
[00:09.50] we were counting the lanterns twice
[00:15.00] hold the evening in your pocket
[00:20.00] marmalade skies are calling us home
[00:30.00] oh the clocks are all sleeping
[00:34.00] marmalade skies are calling us home
[00:40.00] gather the lanterns again
[00:50.00] oh the clocks are all sleeping
[00:54.00] marmalade skies are calling us home
"""


def test_norm_and_similarity():
    assert norm("Don’t Stop, believin'!") == "dont stop believin"
    assert similarity("paper boats on a copper river", "Paper boats on a copper river!") > 0.95
    assert similarity("paper boats on a copper river", "paper boat on the copper river") > 0.65
    assert similarity("paper boats on a copper river", "hold the evening in your pocket") < 0.4
    assert similarity("", "anything") == 0.0


def test_parse_lrc_skips_metadata_and_orders():
    lrc = parse_lrc(LRC)
    assert lrc[0] == (4.0, "paper boats on a copper river")
    assert [t for t, _ in lrc] == sorted(t for t, _ in lrc)
    assert len(lrc) == 9
    assert parse_lrc("[00:01.5] a\n[00:00.25] b\nno stamp\n[00:03.00]   ") == [(0.25, "b"), (1.5, "a")]
    assert parse_lrc("[00:10.00][00:20.00] chorus") == [(10.0, "chorus"), (20.0, "chorus")]
    assert parse_lrc("") == []


def test_parse_identification_valid_and_fallbacks():
    ok = parse_identification('{"title": "Placeholder Song", "artist": "Nobody", "confidence": 0.8}')
    assert ok and ok.title == "Placeholder Song" and ok.artist == "Nobody" and ok.confidence == 0.8
    fenced = parse_identification('```json\n{"title":"A","artist":"B","confidence":1}\n```')
    assert fenced and fenced.title == "A"
    for bad in [None, "", "null", "not json", "[]", '{"title":"A"}',
                '{"title":"A","artist":"B","confidence":0.1}',        # too unsure
                '{"title":"A","artist":"B","confidence":"high"}',
                '{"title":"A","artist":"B","confidence":2}',
                '{"title":"A","artist":"B","confidence":true}',
                '{"title":"", "artist":"B","confidence":0.9}',
                json.dumps({"title": "x" * 200, "artist": "B", "confidence": 0.9}),
                json.dumps({"title": "line one\nline two", "artist": "B", "confidence": 0.9})]:
        assert parse_identification(bad) is None


def test_verify_match():
    lrc = parse_lrc(LRC)
    good = ["paper boats on a copper river", "we were counting the lanterns twice"]
    assert verify_match(good, lrc) > 0.9
    assert verify_match(["paper boats on a copper river"], lrc) > 0.9          # one long phrase is enough
    assert verify_match(["paper boats"], lrc) == 0.0                           # too little heard
    unrelated = ["please take your seats everyone", "the meeting will start shortly"]
    assert verify_match(unrelated, lrc) < 0.4
    assert verify_match(good, []) == 0.0


def test_transcript_buffer_keeps_recent_only():
    b = TranscriptBuffer(span=15)
    b.add(0, "first"); b.add(10, "second"); b.add(20, "third")
    assert b.lines(20) == ["second", "third"]
    assert b.text(40) == ""


def test_tracker_locks_and_keeps_time():
    tr = SongTracker(parse_lrc(LRC))
    assert tr.current(0) is None and not tr.locked
    assert tr.observe("hold the evening in your pocket", now=100.0)       # song time 15.0
    assert tr.position(100.0) == 15.0
    assert tr.position(104.0) == 19.0
    idx, cur, nxt = tr.current(104.7)                                      # 19.7 (+0.15 s lead) → still line 3
    assert cur == "hold the evening in your pocket" and nxt == "marmalade skies are calling us home"
    idx, cur, nxt = tr.current(105.2)                                      # 20.2 → next line
    assert cur == "marmalade skies are calling us home"


def test_tracker_ignores_noise_and_short_input():
    tr = SongTracker(parse_lrc(LRC))
    assert not tr.observe("the meeting will start shortly", 1.0)
    assert not tr.observe("hmm", 2.0)
    assert not tr.locked


def test_tracker_drift_correction():
    tr = SongTracker(parse_lrc(LRC))
    tr.observe("paper boats on a copper river", now=50.0)                  # song 4.0 → offset -46
    # the music actually runs 2.5 s ahead of our local clock by the time the next line is heard
    assert tr.observe("we were counting the lanterns twice", now=53.0)     # song 9.5 → offset -43.5
    assert abs(tr.position(53.0) - 9.5) < 1e-6
    assert tr.last_match == 53.0


def test_tracker_repeated_chorus_prefers_nearest_to_prediction():
    tr = SongTracker(parse_lrc(LRC))
    tr.observe("oh the clocks are all sleeping", now=0.0)                  # ambiguous: 30s or 50s
    first = tr.position(0.0)
    assert first in (30.0, 50.0)
    # 4 s later the chorus line is sung; whichever pass we locked, the chorus line nearest the
    # predicted position (first + 4) must win, not an earlier or later pass.
    tr2 = SongTracker(parse_lrc(LRC))
    tr2.observe("hold the evening in your pocket", now=0.0)                # song 15
    tr2.observe("marmalade skies are calling us home", now=5.0)            # predicted 20 → the 20.0 pass
    assert abs(tr2.position(5.0) - 20.0) < 1e-6
    tr2.observe("oh the clocks are all sleeping", now=15.0)                # predicted 30 → the 30.0 pass
    assert abs(tr2.position(15.0) - 30.0) < 1e-6
    tr2.observe("marmalade skies are calling us home", now=39.0)           # predicted 54 → the 54.0 pass, not 20/34
    assert abs(tr2.position(39.0) - 54.0) < 1e-6


def test_tracker_gap_tolerated_then_lost():
    tr = SongTracker(parse_lrc(LRC))
    tr.observe("paper boats on a copper river", now=0.0)
    assert not tr.lost(10.0)                                                # tolerate a gap
    assert tr.current(10.0)[1] == "we were counting the lanterns twice"     # the local clock keeps going
    assert not tr.lost(15.0)
    assert tr.lost(15.5)
    assert tr.observe("gather the lanterns again", now=16.0)                # a new match re-locks
    assert not tr.lost(20.0)


def test_current_at_end_has_no_next():
    tr = SongTracker(parse_lrc(LRC))
    tr.observe("marmalade skies are calling us home", now=0.0)             # ambiguous; last is fine
    tr.offset = 100.0                                                       # song time far past the end
    idx, cur, nxt = tr.current(0.0)
    assert cur == "marmalade skies are calling us home" and nxt == ""
