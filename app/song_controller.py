"""Per-connection Song mode: identify the song from heard words, look up synced lyrics, follow along.

Kept out of main.py so the hook there is a few lines. Everything is in memory for the session.
Only the current and next lyric line ever leave the server, and no lyric text is logged.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from . import backends, config
from .limits import limits
from .song import SongTracker, TranscriptBuffer, norm, verify_match, VERIFY_THRESHOLD
from .telemetry import log_event

EST_IDENTIFY = 0.003          # same order as one Spark scene call; checked against the daily budget
MIN_WORDS_TO_TRY = 6
TICK_S = 0.25
PARTIAL_MIN_WORDS = 3

Send = Callable[..., Awaitable[None]]


class SongController:
    def __init__(self, send: Send, ip: str, live: bool, clock: Callable[[], float] = time.monotonic,
                 identifier=None, source=None):
        self.send, self.ip, self.live, self.clock = send, ip, live, clock
        self.identifier = identifier or backends.song_identifier(live)
        self.source = source or backends.lyrics_source(live)
        self.buffer = TranscriptBuffer()
        self.tracker: SongTracker | None = None
        self.info: tuple[str, str] | None = None
        self.attempts = 0
        self.last_attempt: float | None = None
        self.cache: dict[tuple[str, str], list[tuple[float, str]] | None] = {}
        self.given_up = False
        self._last_idx: int | None = None
        self._task: asyncio.Task | None = None
        self._busy = False

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        await self.send(type="song", state="listening")
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self.tracker = None

    # ------------------------------------------------------------------ input from the lyrics ASR
    def feed(self, ev: dict) -> None:
        """Called for every lyrics ASR event (cheap, sync)."""
        t = ev.get("type")
        text = (ev.get("transcript") or "").strip()
        if not text:
            return
        now = self.clock()
        if t == "speechComplete":
            self.buffer.add(now, text)
            if self.tracker:
                self.tracker.observe(text, now)
        elif t == "transcript" and not ev.get("final") and self.tracker:
            if len(norm(text).split()) >= PARTIAL_MIN_WORDS:
                self.tracker.observe(text, now)

    # ------------------------------------------------------------------ loop
    async def _run(self) -> None:
        while True:
            await asyncio.sleep(TICK_S)
            now = self.clock()
            if self.tracker:
                if self.tracker.lost(now):
                    log_event("song_lost")
                    self.tracker, self._last_idx = None, None
                    await self.send(type="song", state="lost")
                    continue
                cur = self.tracker.current(now)
                if cur and cur[0] != self._last_idx:
                    self._last_idx = cur[0]
                    await self.send(type="song_line", idx=cur[0], cur=cur[1], next=cur[2])
            elif not self._busy and self._may_try(now):
                self._busy = True
                try:
                    await self._attempt(now)
                finally:
                    self._busy = False

    def _may_try(self, now: float) -> bool:
        if self.given_up or self.attempts >= config.SONG_MAX_ATTEMPTS:
            return False
        if self.last_attempt is not None and now - self.last_attempt < config.LIMIT_SONG[1]:
            return False
        return len(norm(self.buffer.text(now)).split()) >= MIN_WORDS_TO_TRY

    async def _attempt(self, now: float) -> None:
        if self.live and not limits.can_spend(EST_IDENTIFY):
            await self._give_up("budget")
            return
        if not limits.allow(self.ip, "song"):
            return                                   # per-IP spacing; try again next tick
        self.attempts += 1
        self.last_attempt = now
        heard_lines = self.buffer.lines(now)
        ident = None
        try:
            ident = await asyncio.wait_for(self.identifier.identify(" ".join(heard_lines)), config.TIMEOUT_SPARK * 2 + 2)
        except Exception as e:                       # any failure = not recognised
            log_event("song_id_failed", detail=type(e).__name__)
        lrc = None
        if ident:
            key = (ident.title.lower(), ident.artist.lower())
            if key not in self.cache:
                try:
                    self.cache[key] = await self.source.find(ident.title, ident.artist)
                except Exception as e:
                    log_event("song_lookup_failed", detail=type(e).__name__)
                    self.cache[key] = None
            lrc = self.cache[key]
        ok = bool(lrc) and verify_match(heard_lines, lrc) >= VERIFY_THRESHOLD
        if ok:
            tr = SongTracker(lrc)
            now2 = self.clock()
            for line in reversed(self.buffer.lines(now2)):     # lock on the most recent heard line that matches
                if tr.observe(line, now2):
                    break
            if tr.locked:
                self.tracker, self.info, self._last_idx = tr, (ident.title, ident.artist), None
                log_event("song_found", attempts=self.attempts)
                await self.send(type="song", state="found", title=ident.title, artist=ident.artist,
                                credit="lyrics via LRCLIB")
                return
        if self.attempts >= config.SONG_MAX_ATTEMPTS:
            await self._give_up("nomatch")

    async def _give_up(self, why: str) -> None:
        self.given_up = True
        log_event("song_give_up", reason=why)
        await self.send(type="song", state="none", reason=why)
