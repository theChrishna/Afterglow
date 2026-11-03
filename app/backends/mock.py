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


class MockSegmenter:
    """Offline silhouette: a swaying head-and-shoulders shape, same output format as SAM."""

    name = "mock"

    async def segment(self, jpeg: bytes, frame_w: int, frame_h: int) -> dict | None:
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
        la = Image.merge("LA", (Image.new("L", (w, h), 255), alpha))
        out = io.BytesIO()
        la.save(out, "PNG")
        log_stage("sam", (time.perf_counter() - t0) * 1000, True, self.name)
        return {"png": base64.b64encode(out.getvalue()).decode(), "bounds": [left, top, left + w, top + h],
                "frame": [frame_w, frame_h], "confidence": 1.0, "objects": 1, "decode_ms": 0.0, "raster": [w, h]}
