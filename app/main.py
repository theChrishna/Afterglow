"""Afterglow server: static page, health, backdrops, and the /ws/stage cue loop."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import OrderedDict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import backends, config
from .backends import BackendError
from .limits import limits
from .sam_mask import jpeg_size
from .backends.mock import RELATIVE_WORDS
from .scene import DEFAULT_SCENE, Scene, bank_scene, match_bank
from .telemetry import log_event, log_stage, summary

app = FastAPI(title="Afterglow", docs_url=None, redoc_url=None)
config.BANK_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/backdrops", StaticFiles(directory=config.BANK_DIR), name="backdrops")

MAX_UTTERANCE_BYTES = 30 * 48000  # 30 s of 24 kHz s16 mono
CH_COMMAND, CH_LYRICS = 0x01, 0x02
MAX_FRAME_BYTES = 64 * 1024
EST_ASR = 0.002
EST_SPARK = 0.003

_generated: OrderedDict[str, bytes] = OrderedDict()  # generated backdrops, newest last
_GENERATED_MAX = 40


async def _close_later(session, delay: float = 6.0) -> None:
    """Give a stopped stream time to flush its last words, then make sure it is closed."""
    await asyncio.sleep(delay)
    await session.close()


def client_ip(headers, client) -> str:
    """Real client IP behind Render's proxy. Never trust the first X-Forwarded-For entry:
    clients can set it themselves; the proxy appends the real address at the end."""
    for h in ("true-client-ip", "cf-connecting-ip"):
        if headers.get(h):
            return headers[h].strip()
    fwd = headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return client.host if client else "unknown"


def bank_url(scene: Scene) -> str:
    return f"/backdrops/{scene.nearest_backdrop}.webp"


@app.get("/")
async def index():
    return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health():
    return JSONResponse({
        "mode": "mock" if config.MOCK else "live",
        "asr_strategy": config.ASR_STRATEGY,
        "budget": limits.status(),
        "latency": summary(),
    })


@app.get("/api/backdrop/{bid}")
async def generated_backdrop(bid: str):
    data = _generated.get(bid)
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})


class Stage:
    """One browser connection: push-to-talk audio in, transcripts/scenes/backdrops out."""

    def __init__(self, ws: WebSocket, ip: str):
        self.ws, self.ip = ws, ip
        self.scene: Scene = DEFAULT_SCENE
        self.asr = None
        self.asr_bytes = 0
        self.lyrics = None
        self.cue_seq = 0
        self._send_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def send(self, **msg) -> None:
        async with self._send_lock:
            try:
                await self.ws.send_text(json.dumps(msg))
            except Exception:
                pass  # client gone; the receive loop will notice

    async def status(self, state: str, detail: str = "") -> None:
        await self.send(type="status", state=state, detail=detail)

    async def run(self) -> None:
        await self.send(type="hello", mode="mock" if config.MOCK else "live",
                        scene=self.scene.model_dump(), backdrop=bank_url(self.scene))
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    self.on_audio(msg["bytes"])
                elif msg.get("text") is not None:
                    await self.on_control(msg["text"])
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if self.asr:
                await self.asr.close()
            if self.lyrics:
                await self.lyrics.close()
            for t in list(self._tasks):
                t.cancel()

    def on_audio(self, packet: bytes) -> None:
        """Binary frames carry a 1-byte channel tag: 0x01 = held-key command, 0x02 = lyrics."""
        if not packet or len(packet) > MAX_FRAME_BYTES:
            return
        channel, frame = packet[0], packet[1:]
        if channel == CH_LYRICS:
            self.on_lyrics_audio(frame)
            return
        if channel != CH_COMMAND or not self.asr:
            return
        if self.asr_bytes + len(frame) > MAX_UTTERANCE_BYTES:
            self.spawn(self.end_ptt())  # runaway mic: close the utterance
            return
        self.asr_bytes += len(frame)
        self.asr.send_audio(frame)

    async def on_control(self, raw: str) -> None:
        try:
            m = json.loads(raw)
        except ValueError:
            return
        kind = m.get("type")
        if kind == "ptt_start":
            await self.start_ptt()
        elif kind == "ptt_end":
            self.spawn(self.end_ptt())
        elif kind == "lyrics_start":
            await self.start_lyrics()
        elif kind == "lyrics_stop":
            await self.stop_lyrics("stopped")
        elif kind == "text_cue":
            text = str(m.get("text", "")).strip()[:300]
            if text:
                if not limits.allow(self.ip, "cue"):
                    await self.status("limited", "Too many cues; wait a few seconds.")
                    return
                self.spawn(self.handle_cue(text, time.perf_counter(), via="text"))

    # ---------------------------------------------------------------- lyrics (continuous speech)

    async def start_lyrics(self) -> None:
        if self.lyrics:
            return
        if limits.seconds_left(self.ip, "lyrics", config.LYRICS_SECONDS_PER_IP) <= 0:
            await self.send(type="lyrics_state", on=False, reason="used",
                            detail=f"Lyrics are limited to {config.LYRICS_SECONDS_PER_IP // 60} min per visitor per day.")
            return
        live = not config.MOCK and limits.can_spend(EST_ASR)
        if not config.MOCK and not live:
            await self.send(type="lyrics_state", on=False, reason="budget", detail="Lyrics paused: daily budget reached.")
            return

        async def on_event(ev: dict) -> None:
            t = ev.get("type")
            if t == "transcript" and not ev.get("final"):
                await self.send(type="lyric", text=ev.get("transcript", ""), done=False)
            elif t == "speechComplete":
                await self.send(type="lyric", text=ev.get("transcript", ""), done=True)
            elif t == "error":
                await self.stop_lyrics("error")

        self.lyrics = backends.lyrics_session(on_event, live)
        try:
            await self.lyrics.start()
        except Exception as e:
            log_stage("lyrics_start", None, False, self.lyrics.name, error=type(e).__name__)
            self.lyrics = None
            await self.send(type="lyrics_state", on=False, reason="error", detail="Lyrics unavailable right now.")
            return
        log_event("lyrics_start", backend=self.lyrics.name)
        await self.send(type="lyrics_state", on=True,
                        left_s=round(limits.seconds_left(self.ip, "lyrics", config.LYRICS_SECONDS_PER_IP)))

    def on_lyrics_audio(self, frame: bytes) -> None:
        if not self.lyrics:
            return
        limits.use_seconds(self.ip, "lyrics", len(frame) / 48000)
        if limits.seconds_left(self.ip, "lyrics", config.LYRICS_SECONDS_PER_IP) <= 0:
            self.spawn(self.stop_lyrics("used"))
            return
        self.lyrics.send_audio(frame)

    async def stop_lyrics(self, reason: str) -> None:
        session, self.lyrics = self.lyrics, None
        if session is None:
            return
        session.stop()  # server flushes and closes; the session task charges the audio
        self.spawn(_close_later(session))
        detail = {"used": f"Lyrics time used up ({config.LYRICS_SECONDS_PER_IP // 60} min per visitor per day).",
                  "error": "Lyrics stream dropped; press L to restart."}.get(reason, "")
        await self.send(type="lyrics_state", on=False, reason=reason, detail=detail)

    # ---------------------------------------------------------------- commands (hold to talk)

    async def start_ptt(self) -> None:
        if self.asr:
            await self.asr.close()
            self.asr = None
        if not limits.allow(self.ip, "cue"):
            await self.status("limited", "Too many cues; wait a few seconds.")
            return
        live = not config.MOCK and limits.can_spend(EST_ASR)
        if not config.MOCK and not live:
            await self.status("limited", "Voice paused: daily budget reached. Type a cue instead.")
            return

        async def on_partial(text: str) -> None:
            await self.send(type="transcript", final=False, text=text)

        self.asr = backends.asr_session(on_partial, live)
        self.asr_bytes = 0
        try:
            await self.asr.start()
        except Exception as e:  # never let a connect error kill the socket
            log_stage("asr_start", None, False, self.asr.name, error=type(e).__name__)
            self.asr = None
            await self.status("error", "Voice service unavailable; type a cue instead.")
            return
        await self.status("listening")

    async def end_ptt(self) -> None:
        asr, self.asr = self.asr, None
        if asr is None:
            return
        t_release = time.perf_counter()
        await self.status("transcribing")
        try:
            text = await asr.finish()
        except BackendError as e:
            log_event("asr_failed", detail=str(e)[:200])
            await self.status("error", "Didn't catch that. Keeping the current scene.")
            return
        finally:
            self.spawn(asr.close())
        if not text:
            await self.status("ready", "Heard nothing.")
            return
        await self.send(type="transcript", final=True, text=text)
        await self.handle_cue(text, t_release, via="voice")

    async def handle_cue(self, text: str, t0: float, via: str) -> None:
        self.cue_seq += 1
        seq = self.cue_seq
        # Instant keyword guess so the stage reacts within ~0.5 s; Spark's scene refines it.
        guess_id, score = match_bank(text, ignore=RELATIVE_WORDS)
        if score and guess_id != self.scene.nearest_backdrop:
            guess = bank_scene(guess_id)
            await self.send(type="scene", scene=guess.model_dump(), backdrop=bank_url(guess),
                            source="instant", cue=text)
            log_stage("cue_to_instant", (time.perf_counter() - t0) * 1000, True, "keywords", via=via)
        await self.status("thinking")
        live = not config.MOCK and limits.can_spend(EST_SPARK)
        model = backends.scene_model(live)
        try:
            result = await asyncio.wait_for(model.make_scene(text, self.scene), config.TIMEOUT_SPARK * 2 + 2)
        except (BackendError, asyncio.TimeoutError) as e:
            log_event("scene_failed", detail=str(e)[:200] or type(e).__name__)
            await self.status("error", "Scene update failed. Keeping the current scene.")
            return
        if seq != self.cue_seq:
            return  # a newer cue superseded this one
        self.scene = result.scene
        await self.send(type="scene", scene=self.scene.model_dump(), backdrop=bank_url(self.scene),
                        source=model.name, cue=text)
        log_stage("cue_to_scene", (time.perf_counter() - t0) * 1000, True, model.name, via=via)
        await self.status("ready", "" if live or config.MOCK else "Offline mode: daily budget reached.")
        self.spawn(self.generate_backdrop(self.scene, seq))

    async def generate_backdrop(self, scene: Scene, seq: int) -> None:
        if not limits.allow(self.ip, "image"):
            return  # bank image stays; a fresh one comes with a later cue
        live = not config.MOCK and limits.can_spend(config.PRICE_IMAGE)
        if not config.MOCK and not live:
            return
        try:
            data = await backends.image_model(live).generate(scene.backdrop_prompt)
        except BackendError:
            return  # keep bank image
        if not data:
            return
        if live:
            limits.charge("image", config.PRICE_IMAGE)
        bid = uuid.uuid4().hex[:12]
        _generated[bid] = data
        while len(_generated) > _GENERATED_MAX:
            _generated.popitem(last=False)
        if seq == self.cue_seq:
            await self.send(type="backdrop", url=f"/api/backdrop/{bid}", generated=True)


MAX_FRAME_JPEG = 400_000


def _sam_refusal(error: str, status: int, ip: str, detail: str) -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail,
                         "perform_left_s": round(limits.perform_remaining(ip))}, status_code=status)


@app.post("/api/silhouette")
async def silhouette(request: Request):
    """One webcam frame (JPEG) -> the performer's mask. Gated by Perform time per IP,
    a per-IP rate limit and the daily budget."""
    ip = client_ip(request.headers, request.client)
    if limits.perform_remaining(ip) <= 0:
        return _sam_refusal("perform_time_up", 429, ip,
                            f"Perform mode is limited to {limits.perform_seconds // 60} min per visitor per day.")
    if not limits.allow(ip, "sam"):
        return _sam_refusal("too_fast", 429, ip, "One frame every 3 s.")
    if int(request.headers.get("content-length") or 0) > MAX_FRAME_JPEG:
        return _sam_refusal("too_large", 413, ip, "Frame too large.")
    jpeg = await request.body()
    try:
        if len(jpeg) > MAX_FRAME_JPEG:
            raise ValueError("too large")
        fw, fh = await asyncio.to_thread(jpeg_size, jpeg)
    except Exception:
        return _sam_refusal("bad_frame", 400, ip, "Send one JPEG frame.")
    live = not config.MOCK and limits.can_spend(config.PRICE_SAM)
    if not config.MOCK and not live:
        return _sam_refusal("budget", 503, ip, "Ghost echo paused: daily budget reached.")
    limits.start_perform(ip)
    seg = backends.segmenter(live)
    t0 = time.perf_counter()
    try:
        as_png = request.headers.get("x-mask-format") == "png"
        mask = await asyncio.wait_for(seg.segment(jpeg, fw, fh, as_png), config.TIMEOUT_SAM)
    except (BackendError, asyncio.TimeoutError):
        return _sam_refusal("sam_failed", 502, ip, "Silhouette unavailable; keeping the last echo.")
    finally:
        if live:
            limits.charge("sam", config.PRICE_SAM)  # billed per image, match or not
    log_stage("silhouette_total", (time.perf_counter() - t0) * 1000, True, seg.name,
              matched=mask is not None)
    return JSONResponse({"mask": mask, "source": seg.name,
                         "perform_left_s": round(limits.perform_remaining(ip))})


@app.websocket("/ws/stage")
async def ws_stage(ws: WebSocket):
    await ws.accept()
    ip = client_ip(ws.headers, ws.client)
    log_event("stage_connect", mode="mock" if config.MOCK else "live")
    await Stage(ws, ip).run()


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
