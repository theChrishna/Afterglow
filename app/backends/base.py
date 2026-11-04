"""One interface per model call. `meta_api` and `mock` both implement these."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from ..scene import Scene

PartialCallback = Callable[[str], Awaitable[None]]
EventCallback = Callable[[dict], Awaitable[None]]


class BackendError(Exception):
    """Any failed/timed-out model call. Callers keep the last good state."""


class ASRSession(Protocol):
    name: str

    async def start(self) -> None:
        """Begin connecting. Audio sent before the upstream is ready is buffered."""

    def send_audio(self, pcm16: bytes) -> None:
        """Queue 24 kHz mono s16le PCM."""

    async def finish(self) -> str:
        """Signal end of speech and wait for the final transcript."""

    async def close(self) -> None: ...


@dataclass
class SceneResult:
    scene: Scene
    cost_usd: float = 0.0
    attempts: int = 1
    meta: dict = field(default_factory=dict)


class SceneModel(Protocol):
    name: str

    async def make_scene(self, cue: str, previous: Scene) -> SceneResult: ...


class ImageModel(Protocol):
    name: str

    async def generate(self, prompt: str) -> bytes | None:
        """Return a 1280x720 webp, or None if nothing new was produced."""
