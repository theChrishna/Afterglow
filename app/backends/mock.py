"""Offline backends: canned transcripts, keyword scenes, bank backdrops. No network, no spend."""

from __future__ import annotations

import asyncio
import itertools
import time

from .. import config
from ..scene import Scene, bank_scene, match_bank, nearest_bank_by_keywords
from ..telemetry import log_stage
from .base import EventCallback, PartialCallback, SceneResult

# Same cues as DEMO.md, so a mock run rehearses the real show.
CANNED_CUES = [
    "Make it feel like a rainy city at 3am",
    "Switch background mood to warm retro synth neon",
    "Take us into deep space, slow and floating",
    "Misty forest at dawn, very calm",
    "Now set everything on fire, fast and loud",
    "Cold arctic night with the northern lights",
    "Brighter, and a bit faster",
    "Drop us underwater, calm and blue",
]
_cues = itertools.cycle(CANNED_CUES)


class MockASRSession:
    name = "mock"

    def __init__(self, on_partial: PartialCallback | None = None):
        self.on_partial = on_partial
        self.audio_bytes = 0
        self.t_end = None

    async def start(self) -> None:
        pass

    def send_audio(self, pcm16: bytes) -> None:
        self.audio_bytes += len(pcm16)

    async def finish(self) -> str:
        self.t_end = time.perf_counter()
        cue = next(_cues)
        if self.on_partial:
            await self.on_partial(" ".join(cue.split()[:3]))
        await asyncio.sleep(0.45)
        log_stage("asr_final_after_release", (time.perf_counter() - self.t_end) * 1000, True, self.name)
        return cue

    async def close(self) -> None:
        pass


CANNED_LYRICS = [
    "city lights are bleeding through the rain",
    "I keep your name inside the static",
    "we were neon we were never meant to fade",
    "hold the note until the morning breaks",
]


# An INVENTED song for testing Song mode offline. Placeholder title, invented lines; not a real song.
MOCK_SONG_TITLE, MOCK_SONG_ARTIST = "Placeholder Song", "Nobody in Particular"
MOCK_SONG_LINES = [
    "paper boats on a copper river",
    "we were counting the lanterns twice",
    "hold the evening in your pocket",
    "marmalade skies are calling us home",
    "oh the clocks are all sleeping",
    "marmalade skies are calling us home",
    "gather the lanterns again",
]
MOCK_WORD_S, MOCK_GAP_S = 0.32, 1.4      # pacing of the mock singer (tests shorten these)


def mock_song_lrc() -> list[tuple[float, str]]:
    """Timestamps consistent with how MockLyricsSession paces its lines."""
    out, t = [], 2.0
    for line in MOCK_SONG_LINES:
        out.append((t, line))
        t += len(line.split()) * MOCK_WORD_S + MOCK_GAP_S
    return out


class MockSongIdentifier:
    name = "mock"

    async def identify(self, heard: str):
        from ..song import Identification, similarity
        if any(similarity(heard, l) >= 0.5 or l in heard.lower() for l in MOCK_SONG_LINES):
            return Identification(MOCK_SONG_TITLE, MOCK_SONG_ARTIST, 0.9)
        return None


class MockLyricsSource:
    name = "mock"

    async def find(self, title: str, artist: str):
        return mock_song_lrc() if title == MOCK_SONG_TITLE else None


class MockLyricsSession:
    """Offline lyrics stream: while audio keeps arriving, emits a canned line word by word
    in the same event shapes as ENDPOINTING mode (transcript partials, speechComplete).
    `sing_song()` switches it from the canned lines to the invented song."""

    name = "mock"

    def __init__(self, on_event: EventCallback):
        self.on_event = on_event
        self.audio_bytes = 0
        self._last_audio = 0.0
        self._task: asyncio.Task | None = None
        self.source = CANNED_LYRICS

    def sing_song(self) -> None:
        self.source = MOCK_SONG_LINES

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def send_audio(self, pcm16: bytes) -> None:
        self.audio_bytes += len(pcm16)
        self._last_audio = time.monotonic()

    async def _run(self) -> None:
        turn = 0
        src = self.source
        while True:
            if self.source is not src:           # switched to the song: drop any half-sung canned line
                src, turn = self.source, 0
            line = src[turn % len(src)]
            words = line.split()
            await self.on_event({"type": "speechStart", "turnId": turn})
            switched = False
            for n in range(1, len(words) + 1):
                while time.monotonic() - self._last_audio > 0.5:  # paused: no mic audio
                    await asyncio.sleep(0.1)
                await asyncio.sleep(MOCK_WORD_S)
                if self.source is not src:
                    switched = True
                    break
                await self.on_event({"type": "transcript", "final": False, "transcript": " ".join(words[:n])})
            if switched:
                continue
            await self.on_event({"type": "speechComplete", "turnId": turn, "transcript": line})
            turn += 1
            await asyncio.sleep(MOCK_GAP_S)

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def close(self) -> None:
        self.stop()


_RELATIVE = {
    "bright": ("lighting", "intensity", +0.2), "dark": ("lighting", "intensity", -0.25),
    "dim": ("lighting", "intensity", -0.25), "warm": ("lighting", "warmth", +0.4),
    "cold": ("lighting", "warmth", -0.4), "cool": ("lighting", "warmth", -0.4),
    "fast": ("shader", "speed", +0.4), "slow": ("shader", "speed", -0.3),
}
_LIMITS = {"intensity": (0, 1), "warmth": (-1, 1), "speed": (0, 2)}
RELATIVE_WORDS = frozenset(_RELATIVE) | {"calm", "fast", "slow", "warm", "cold"}


class MockSceneModel:
    name = "mock"

    async def make_scene(self, cue: str, previous: Scene) -> SceneResult:
        t0 = time.perf_counter()
        await asyncio.sleep(0.5)
        text = cue.lower()
        bank_id, score = match_bank(text, ignore=RELATIVE_WORDS)
        if score:
            scene = bank_scene(bank_id)
        else:
            scene = previous.model_copy(deep=True)
        for word, (group, field, delta) in _RELATIVE.items():
            if word in text:
                obj = getattr(scene, group)
                lo, hi = _LIMITS[field]
                setattr(obj, field, round(min(hi, max(lo, getattr(obj, field) + delta)), 2))
        log_stage("spark", (time.perf_counter() - t0) * 1000, True, self.name)
        return SceneResult(scene=scene)


class MockImageModel:
    """Pretends to generate: after a delay, returns the bank image for the prompt's mood."""

    name = "mock"

    async def generate(self, prompt: str) -> bytes | None:
        t0 = time.perf_counter()
        await asyncio.sleep(2.0)
        path = config.BANK_DIR / f"{nearest_bank_by_keywords(prompt)}.webp"
        data = path.read_bytes() if path.exists() else None
        log_stage("image", (time.perf_counter() - t0) * 1000, True, self.name, found=data is not None)
        return data


class MockSegmenter:
    """Offline silhouette: a swaying head-and-shoulders shape, same output format as SAM."""

    name = "mock"

    async def segment(self, jpeg: bytes, frame_w: int, frame_h: int, as_png: bool = False) -> dict | None:
        import base64
        import io
        import math

        from PIL import Image, ImageDraw

        t0 = time.perf_counter()
        await asyncio.sleep(0.8)
        sway = math.sin(time.time() * 0.7) * frame_w * 0.08
        w, h = int(frame_w * 0.34), int(frame_h * 0.9)
        left = int(frame_w / 2 - w / 2 + sway)
        top = frame_h - h
        alpha = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(alpha)
        head = w * 0.28
        d.ellipse([w / 2 - head / 2, h * 0.04, w / 2 + head / 2, h * 0.04 + head * 1.2], fill=255)
        d.rounded_rectangle([w * 0.42, h * 0.04 + head * 1.1, w * 0.58, h * 0.32], radius=6, fill=255)
        d.rounded_rectangle([w * 0.05, h * 0.3, w * 0.95, h * 1.2], radius=int(w * 0.25), fill=255)
        log_stage("sam", (time.perf_counter() - t0) * 1000, True, self.name)
        out = {"bounds": [left, top, left + w, top + h], "frame": [frame_w, frame_h],
               "confidence": 1.0, "objects": 1, "raster": [w, h]}
        raster = alpha.point(lambda v: 1 if v else 0).tobytes()
        if as_png:
            from ..sam_mask import mask_png
            out["png"] = base64.b64encode(mask_png(raster, w, h)).decode()
        else:
            # Same wire format SAM returns, so the browser decoder path is exercised offline too.
            from meta_sam_parser._mask_codec import _encode_raster
            out["mask"] = {"encoding": "one_bit", "payload": _encode_raster(raster, w, h), "width": w, "height": h}
        return out
