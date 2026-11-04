# Afterglow

A live-performance stage engine. The performer speaks cues (push-to-talk) and the stage reacts:
light and motion change at once, a new backdrop drifts in a few seconds later, and with the camera
on, the performer's silhouette echoes on the stage. Lyrics they say or sing stream onto the screen.

Live: https://afterglow-chia.onrender.com (Render free plan; the first load after idle is slow)

*Built during the hackathon.*

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # put MODEL_API_KEY in .env (never commit it)
.venv/bin/uvicorn app.main:app --port 8000
```

`MOCK=1 .venv/bin/uvicorn app.main:app --port 8000` runs with canned transcripts and keyword
scenes, no API calls and no key needed. Tests: `.venv/bin/pytest`.

See [DEMO.md](DEMO.md) for the cue script.

## Models used (and who made them)

| Job | Model | Where it runs | Maker |
|---|---|---|---|
| Speech to text (commands, lyrics) | Muse Voice Transcribe | Meta Model API | Meta |
| Cue to scene JSON | Muse Spark | Meta Model API | Meta |
| Backdrops (8 pre-generated, new ones live) | Muse Image | Meta Model API | Meta |
| Snapshot silhouette every 6 s ("afterglow" layer) | SAM 3.1 | Meta Model API | Meta |
| **Real-time silhouette (echo, modes)** | **MediaPipe selfie segmenter** | **On-device, in the browser** | **Google, not Meta** |

The real-time silhouette is a Google on-device model. Only the slower 6 s snapshot layer uses
Meta's SAM 3.1.

## Performance modes

Switch with the **Mode** button next to Perform, or press **M** (Off → Composite → Projection).
Choosing a mode turns the camera on.

| Mode | What the audience sees |
|---|---|
| **Off** (default) | The original ghost echo: glowing live silhouette, a rising trail and delayed copies, plus SAM 3.1 snapshots. |
| **Composite** | The live webcam with the background removed (mask as alpha, 2–3 px feather) over the backdrop and shader, under the lyrics. Echo trail optional (off by default, drawn at half strength). |
| **Projection** | For a projector pointed at the performer: scenery everywhere except a live **black** silhouette over the performer, so no light lands on them. **Grow** (0–30 px) widens the black area; **feather** softens its edge. No echo or glow in this mode. |

**Calibration** (Projection mode, press **C**): drag the 4 corner handles until the grid and
crosshairs line up with the stage (a homography), then fine-tune offset X/Y and scale, and set
mirror or flip up/down. The warp is a CSS `matrix3d` on the silhouette layer, so it adds no
per-frame cost. Settings are saved in this browser's localStorage.

Other keys: **F** mirror, **T** latency readout, **P** camera on/off, **L** lyrics, **H** hide controls.

## Latency

Measured with the on-screen readout (**T**) in the Chromium-based in-app browser on a Mac, using a **synthetic camera**
(a 640×360 canvas stream of a still photo, nudged each frame). Not measured with a real webcam.

| | Before (`stable-1100`) | After |
|---|---|---|
| Segmenter call on the main thread (inference + mask handling) | **12.2 ms** | **3.4–3.7 ms** |
| …of which mask → canvas | ~11.5 ms (full float readback + JS loop) | GPU texture, no full readback |
| Segmenter runs per camera frame | capped at ~30/s by a timer | 1 per frame (`requestVideoFrameCallback`) |
| Primary silhouette delay | drawn from the newest mask | newest mask, zero added delay |
| Echo copies delayed by | 7/14/21 frames (~0.23/0.47/0.70 s at 30 fps) | 0.10/0.22/0.38 s, by timestamp |
| Per-frame allocations in the mask path | 1 canvas per frame | none (fixed 40-slot ring) |
| Camera request | 640×360 | 640×360, 60 fps ideal (24 min) |
| Draw loop in Projection (grow 8, feather 3) | n/a | 16.7 ms (holds 60 Hz) |

What changed: segmentation is driven by `requestVideoFrameCallback` (falls back to
`requestAnimationFrame`); MediaPipe runs on its GPU delegate with its own WebGL canvas, and its mask
texture is turned into an alpha mask by one shader pass and GPU-copied into a preallocated ring. If
the GPU path fails, it falls back to reused CPU buffers.

Not measured: true camera-to-photon lag. With the synthetic camera the browser gives no
`captureTime`, so the readout's "cam→draw" figure (~17 ms) only covers frame arrival to draw, not
sensor or display latency. The segmenter's GPU time is also not captured by these main-thread
timings. Inference stays on the main thread; moving it to a worker was not attempted.

## Not verified

- A real webcam (all numbers above use a synthetic canvas camera).
- A real projector: Projection mode and calibration were checked on screen only.
- Phones and tablets: layout checked at 375 px wide in a desktop browser, not on a device.
- Safari and Firefox: `requestVideoFrameCallback`, canvas `filter` (feather) and the GPU mask
  path may behave differently; the fallbacks are in place but were not exercised there.
