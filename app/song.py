"""Song mode logic: no network, no I/O, so it can be unit-tested with plain strings.

Identification (Spark) and lookup (LRCLIB) live in `backends`; this module only does
text matching, LRC parsing, validation and keeping time with a song.
Lyric text is held in memory for the session and never logged or written to disk.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher

LOCK_THRESHOLD = 0.62        # a heard phrase this similar to a lyric line locks the song clock
VERIFY_THRESHOLD = 0.55      # mean best-similarity needed to accept a candidate song
MIN_CONFIDENCE = 0.4         # Spark's own confidence floor
LOST_AFTER_S = 15.0          # no confident match for this long → fall back to plain lyrics
BUFFER_S = 15.0

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_LRC = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def norm(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", text.lower().replace("’", "'").replace("'", "")).split())


def similarity(a: str, b: str) -> float:
    """0..1. Order-insensitive token overlap blended with character-level similarity, so ASR slips
    ("gonna" / "going to", dropped words) still match but unrelated lines don't."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jacc = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, na, nb).ratio()
    return 0.5 * jacc + 0.5 * seq


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """'[mm:ss.xx] line' → [(seconds, line)], sorted. Metadata tags and empty lines are dropped."""
    out: list[tuple[float, str]] = []
    for raw in (text or "").splitlines():
        stamps = list(_LRC.finditer(raw))
        if not stamps:
            continue
        line = raw[stamps[-1].end():].strip()
        if not line:
            continue
        for m in stamps:
            frac = m.group(3) or "0"
            t = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))
            out.append((t, line))
    out.sort(key=lambda x: x[0])
    return out


@dataclass
class Identification:
    title: str
    artist: str
    confidence: float


def parse_identification(content: str | None) -> Identification | None:
    """Validate Spark's JSON. Anything unexpected means 'not recognised'; never raises."""
    if not content:
        return None
    s = content.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\s*|\s*```$", "", s)
    try:
        j = json.loads(s)
    except ValueError:
        return None
    if not isinstance(j, dict):
        return None
    title, artist, conf = j.get("title"), j.get("artist"), j.get("confidence")
    if not isinstance(title, str) or not isinstance(artist, str):
        return None
    title, artist = title.strip(), artist.strip()
    if not title or not artist or len(title) > 120 or len(artist) > 120 or "\n" in title + artist:
        return None                      # also keeps a model from smuggling lyrics through these fields
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        return None
    if conf < MIN_CONFIDENCE:
        return None
    return Identification(title, artist, float(conf))


def verify_match(heard: list[str], lrc: list[tuple[float, str]]) -> float:
    """Mean over heard phrases of the best similarity to any lyric line (0 if too little was heard)."""
    heard = [h for h in heard if len(norm(h).split()) >= 2]
    words = sum(len(norm(h).split()) for h in heard)
    if not lrc or not heard or (len(heard) < 2 and words < 6):
        return 0.0
    return sum(max(similarity(h, line) for _, line in lrc) for h in heard) / len(heard)


class TranscriptBuffer:
    """Final utterances from the last BUFFER_S seconds."""

    def __init__(self, span: float = BUFFER_S):
        self.span = span
        self._items: deque[tuple[float, str]] = deque()

    def add(self, now: float, text: str) -> None:
        text = text.strip()
        if text:
            self._items.append((now, text))
        self.trim(now)

    def trim(self, now: float) -> None:
        while self._items and now - self._items[0][0] > self.span:
            self._items.popleft()

    def lines(self, now: float) -> list[str]:
        self.trim(now)
        return [t for _, t in self._items]

    def text(self, now: float) -> str:
        return " ".join(self.lines(now))


class SongTracker:
    """Follows a song: locks the song clock to a lyric line when the heard words match it, then keeps
    time locally. Each confident match re-syncs (drift correction); with repeated lines (a chorus) the
    match nearest the predicted position wins."""

    def __init__(self, lrc: list[tuple[float, str]]):
        self.lrc = lrc
        self.offset: float | None = None      # song_time = now + offset
        self.last_match: float | None = None  # monotonic time of the last confident match
        self.started: float | None = None

    @property
    def locked(self) -> bool:
        return self.offset is not None

    def position(self, now: float) -> float | None:
        return None if self.offset is None else now + self.offset

    def observe(self, words: str, now: float) -> bool:
        """Feed the latest heard words (a partial or a final). True if this re-synced the clock."""
        if len(norm(words).split()) < 2 or not self.lrc:
            return False
        pred = self.position(now)
        best, best_i = 0.0, -1
        for i, (t, line) in enumerate(self.lrc):
            sc = similarity(words, line)
            if sc < LOCK_THRESHOLD:
                continue
            # prefer the occurrence nearest the predicted position; a small bias so ties go to it
            if pred is not None:
                sc -= min(0.1, abs(t - pred) / 600.0)
            if sc > best:
                best, best_i = sc, i
        if best_i < 0:
            return False
        t_line = self.lrc[best_i][0]
        self.offset = t_line - now
        self.last_match = now
        if self.started is None:
            self.started = now
        return True

    def current(self, now: float) -> tuple[int, str, str] | None:
        """(index, current line, next line) for the predicted position, or None before the first lock."""
        pos = self.position(now)
        if pos is None:
            return None
        idx = -1
        for i, (t, _) in enumerate(self.lrc):
            if t <= pos + 0.15:
                idx = i
            else:
                break
        if idx < 0:
            idx = 0
        nxt = self.lrc[idx + 1][1] if idx + 1 < len(self.lrc) else ""
        return idx, self.lrc[idx][1], nxt

    def lost(self, now: float) -> bool:
        return self.last_match is not None and now - self.last_match > LOST_AFTER_S
