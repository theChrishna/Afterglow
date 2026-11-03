"""Offline backends: canned transcripts, keyword scenes, bank backdrops. No network, no spend."""

from __future__ import annotations

import asyncio
import itertools
import time

from .. import config
from ..scene import Scene, bank_scene, match_bank, nearest_bank_by_keywords
from ..telemetry import log_stage
from .base import PartialCallback, SceneResult

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
