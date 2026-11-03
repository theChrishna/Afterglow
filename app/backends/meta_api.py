"""Real Meta Model API calls. Request shapes follow dev.meta.ai/docs (see docs_notes in README)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time

import httpx
from pydantic import ValidationError
from websockets.asyncio.client import connect

from .. import config
from ..scene import BANK, SCENE_JSON_SCHEMA, Scene
from ..telemetry import log_event, log_stage
from .base import BackendError, PartialCallback, SceneResult

_http: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            base_url=config.BASE_URL,
            headers={"Authorization": f"Bearer {config.MODEL_API_KEY}"},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
    return _http


def _err(e: Exception) -> str:
    """Error text with the key scrubbed, short enough for logs."""
    s = f"{type(e).__name__}: {e}"
    if config.MODEL_API_KEY:
        s = s.replace(config.MODEL_API_KEY, "[REDACTED]")
    return s[:300]


# ------------------------------------------------------------------ ASR (realtime websocket)

_END = object()


class MetaASRSession:
    """Push-to-talk session on wss://api.meta.ai/v1/asr/realtime.

    Connects on start(); audio queued before the handshake ack is flushed in order once
    the server is ready (the docs allow up to 5 s of backlog ahead of processing).
    finish() sends {"type":"endStream"} and waits for the transcript with final=true.
    """

    name = "meta_api"

    def __init__(self, on_partial: PartialCallback | None = None):
        self.on_partial = on_partial
        self._queue: asyncio.Queue = asyncio.Queue()
        self._final: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._task: asyncio.Task | None = None
        self._ws = None
        self.audio_bytes = 0
        self.t_start = 0.0
        self.t_ready: float | None = None
        self.t_end: float | None = None
        self.backlog_at_ready = 0

    async def start(self) -> None:
        self.t_start = time.perf_counter()
        self._task = asyncio.create_task(self._run())

    def send_audio(self, pcm16: bytes) -> None:
        if self.t_end is None and pcm16:
            self.audio_bytes += len(pcm16)
            self._queue.put_nowait(pcm16)

    async def finish(self) -> str:
        if self.t_end is None:
            self.t_end = time.perf_counter()
            self._queue.put_nowait(_END)
        try:
            text = await asyncio.wait_for(asyncio.shield(self._final),
                                          config.TIMEOUT_ASR_CONNECT + config.TIMEOUT_ASR_FINAL)
        except asyncio.TimeoutError as e:
            log_stage("asr_final", None, False, self.name, error="timeout")
            raise BackendError("ASR timed out") from e
        log_stage("asr_final_after_release", (time.perf_counter() - self.t_end) * 1000, True, self.name,
                  audio_s=round(self.audio_s, 2), connect_ms=self._connect_ms(),
                  backlog_s=round(self.backlog_at_ready / 48000, 2))
        return text

    @property
    def audio_s(self) -> float:
        return self.audio_bytes / 48000  # 24 kHz * 2 bytes

    def _connect_ms(self):
        return None if self.t_ready is None else round((self.t_ready - self.t_start) * 1000, 1)

    def _fail(self, msg: str) -> None:
        if not self._final.done():
            self._final.set_exception(BackendError(msg))
            self._final.exception()  # mark retrieved; finish() re-raises via shield

    async def _run(self) -> None:
        reader: asyncio.Task | None = None
        try:
            async with connect(config.ASR_WS_URL, open_timeout=config.TIMEOUT_ASR_CONNECT,
                               max_size=2**22) as ws:
                self._ws = ws
                await ws.send(json.dumps({
                    "authorization": {"accessToken": f"Bearer {config.MODEL_API_KEY}"},
                    "audioEncoding": "PCM_24KHZ",
                    "model": config.ASR_MODEL,
                    "mode": "PUSH_TO_TALK",
                    "languageBias": ["English"],
                }))
                await asyncio.wait_for(self._await_ack(ws), config.TIMEOUT_ASR_CONNECT)
                self.t_ready = time.perf_counter()
                self.backlog_at_ready = sum(len(b) for b in self._queue._queue if b is not _END)  # noqa: SLF001
                log_stage("asr_connect", (self.t_ready - self.t_start) * 1000, True, self.name,
                          backlog_s=round(self.backlog_at_ready / 48000, 2))
                reader = asyncio.create_task(self._read(ws))
                while True:
                    item = await self._queue.get()
                    if item is _END:
                        await ws.send(json.dumps({"type": "endStream"}))
                        break
                    await ws.send(item)
                # Wait for the final transcript and the server's 1000 close.
                await asyncio.wait({reader}, timeout=config.TIMEOUT_ASR_FINAL)
                if not self._final.done():
                    self._fail(f"closed without final transcript (code {ws.close_code})")
        except asyncio.CancelledError:
            self._fail("cancelled")
            raise
        except Exception as e:
            log_stage("asr_session", None, False, self.name, error=_err(e))
            self._fail(_err(e))
        finally:
            if reader and not reader.done():
                reader.cancel()
            self._ws = None
            cost = int(self.audio_s) * config.PRICE_ASR_PER_SEC
            from ..limits import limits  # local import avoids a cycle
            limits.charge("asr", cost)

    @staticmethod
    async def _await_ack(ws) -> None:
        while True:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                continue
            ev = json.loads(msg)
            if ev.get("type") == "error":
                raise BackendError(f"ASR handshake error: {ev.get('message')}")
            if "type" not in ev:  # the ack is the only frame without a type
                return

    async def _read(self, ws) -> None:
        async for m in ws:
            if isinstance(m, bytes):
                continue
            ev = json.loads(m)
            t = ev.get("type")
            if t == "transcript":
                text = (ev.get("transcript") or "").strip()
                if ev.get("final"):
                    if not self._final.done():
                        self._final.set_result(text)
                elif self.on_partial and text:
                    try:
                        await self.on_partial(text)
                    except Exception:
                        pass
            elif t == "error":
                self._fail(f"ASR error: {ev.get('message')}")

    async def close(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass


# ------------------------------------------------------------------ Scene (Muse Spark)

def _system_prompt(previous: Scene) -> str:
    bank = "\n".join(f"- {bid}: {b['label']}" for bid, b in BANK.items())
    return (
        "You are the lighting and visual director for a live stage performance. The performer "
        "speaks a cue; turn it into a scene for the screen behind them.\n"
        "Fields: mood = 2-5 word name. palette = 3 hex colors ordered dark, mid, bright accent. "
        "lighting.intensity 0-1 (overall brightness); lighting.warmth -1 (cold blue) to 1 (warm amber); "
        "lighting.pulse_bpm 0 for steady light, otherwise a musical tempo 60-180. "
        "shader.style: grid = retro synth perspective grid, rain = falling rain streaks and bokeh, "
        "nebula = cosmic gas clouds and stars, smoke = slow drifting fog or heat haze, "
        "aurora = flowing light curtains or underwater caustics, embers = rising sparks and fire. "
        "shader.speed 0-2 (motion speed), shader.grain 0-1 (film grain). "
        "backdrop_prompt = vivid image prompt for a 16:9 abstract stage backdrop, max 25 words, "
        "no text, no people. nearest_backdrop = closest of these pre-made backdrops:\n"
        f"{bank}\n"
        "If the cue is a relative change (brighter, slower, warmer, more intense), adjust the "
        f"current scene instead of replacing it. Current scene: {previous.model_dump_json()}"
    )


class MetaSceneModel:
    name = "meta_api"

    def __init__(self):
        self.strict = True

    async def make_scene(self, cue: str, previous: Scene) -> SceneResult:
        body = {
            "model": config.SPARK_MODEL,
            "reasoning_effort": "minimal",
            "messages": [{"role": "system", "content": _system_prompt(previous)},
                         {"role": "user", "content": cue[:500]}],
        }
        cost, last_err = 0.0, "unknown"
        for attempt in (1, 2):  # retry once on invalid output
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "StageScene", "schema": SCENE_JSON_SCHEMA, "strict": self.strict}}
            t0 = time.perf_counter()
            try:
                r = await http().post("/chat/completions", json=body, timeout=config.TIMEOUT_SPARK)
            except httpx.HTTPError as e:
                last_err = _err(e)
                log_stage("spark", (time.perf_counter() - t0) * 1000, False, self.name,
                          attempt=attempt, error=last_err)
                continue
            ms = (time.perf_counter() - t0) * 1000
            if r.status_code == 400 and self.strict and "strict" in r.text.lower():
                self.strict = False  # strict schema unsupported: fall back to Pydantic-only validation
                log_event("spark_strict_disabled", detail=r.text[:200])
                continue
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                log_stage("spark", ms, False, self.name, attempt=attempt, error=last_err)
                continue
            j = r.json()
            usage = j.get("usage") or {}
            cost += (usage.get("prompt_tokens", 0) * config.PRICE_SPARK_IN
                     + usage.get("completion_tokens", 0) * config.PRICE_SPARK_OUT)
            content = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            try:
                scene = Scene.model_validate_json(content)
            except (ValidationError, ValueError) as e:
                last_err = f"invalid scene: {str(e)[:200]}"
                log_stage("spark", ms, False, self.name, attempt=attempt, error=last_err)
                continue
            log_stage("spark", ms, True, self.name, attempt=attempt,
                      tokens_out=usage.get("completion_tokens"),
                      reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
            from ..limits import limits
            limits.charge("spark", cost)
            return SceneResult(scene=scene, cost_usd=cost, attempts=attempt)
        from ..limits import limits
        limits.charge("spark", cost)
        raise BackendError(f"scene failed after retry: {last_err}")


# ------------------------------------------------------------------ Backdrop (Muse Image)

def to_backdrop_webp(raw: bytes, size=(1280, 720), quality=72) -> bytes:
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=quality, method=4)
    return out.getvalue()


class MetaImageModel:
    name = "meta_api"

    async def generate(self, prompt: str) -> bytes | None:
        body = {
            "model": config.IMAGE_MODEL,
            "prompt": prompt[:400],
            "n": 1,
            "size": "1792x1024",
            "response_format": "b64_json",
            "output_format": "webp",
            "reasoning_strength": "low",
            "tool_enablement": {"enable_image_search": False, "enable_web_search": False,
                                "enable_shell": False},
        }
        t0 = time.perf_counter()
        try:
            r = await http().post("/images/generations", json=body, timeout=config.TIMEOUT_IMAGE)
        except httpx.HTTPError as e:
            log_stage("image", (time.perf_counter() - t0) * 1000, False, self.name, error=_err(e))
            raise BackendError(_err(e)) from e
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            log_stage("image", ms, False, self.name, error=f"HTTP {r.status_code}: {r.text[:200]}")
            raise BackendError(f"image HTTP {r.status_code}")
        data = (r.json().get("data") or [{}])[0]
        if not data.get("b64_json"):
            log_stage("image", ms, False, self.name, error="no image data")
            raise BackendError("no image data")
        webp = await asyncio.to_thread(to_backdrop_webp, base64.b64decode(data["b64_json"]))
        log_stage("image", ms, True, self.name, out_bytes=len(webp))
        return webp


# ------------------------------------------------------------------ Silhouette (SAM 3.1)

class MetaSegmenter:
    name = "meta_api"

    async def segment(self, jpeg: bytes, frame_w: int, frame_h: int, as_png: bool = False) -> dict | None:
        from ..sam_mask import main_subject

        body = {
            "model": config.SAM_MODEL,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "person"},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()},
            ]}],
            "stream": False,
            "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
        }
        t0 = time.perf_counter()
        try:
            r = await http().post("/responses", json=body, timeout=config.TIMEOUT_SAM)
        except httpx.HTTPError as e:
            log_stage("sam", (time.perf_counter() - t0) * 1000, False, self.name, error=_err(e))
            raise BackendError(_err(e)) from e
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            log_stage("sam", ms, False, self.name, error=f"HTTP {r.status_code}: {r.text[:200]}")
            raise BackendError(f"SAM HTTP {r.status_code}")
        j = r.json()
        text = j.get("output_text") if isinstance(j.get("output_text"), str) else "".join(
            c.get("text", "") for item in j.get("output", []) or [] for c in item.get("content", []) or []
            if c.get("type") == "output_text")
        try:
            result = await asyncio.to_thread(main_subject, text, frame_w, frame_h, as_png)
        except Exception as e:  # malformed output: treat as a failed frame, keep the last ghost
            log_stage("sam", ms, False, self.name, error=f"parse: {_err(e)}")
            raise BackendError("SAM parse failed") from e
        log_stage("sam", ms, True, self.name, matches=0 if result is None else result["objects"],
                  server_decode_ms=None if result is None else result.get("decode_ms"))
        return result
