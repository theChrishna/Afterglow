# Afterglow

A live-performance stage engine. Say a mood and the stage becomes it: the performer speaks cues
(push-to-talk) or taps a mood chip, light and motion change at once, and the refined scene lands a
few seconds later. With the camera on, the performer's silhouette echoes on the stage, and what
they say or sing appears as lyrics.

Live: https://afterglow-chia.onrender.com (Render free plan; the first load after idle is slow)

*Built during the Meta Global AI Developer Hackathon.*

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # put MODEL_API_KEY in .env (never commit it)
.venv/bin/uvicorn app.main:app --port 8000
```

`MOCK=1 .venv/bin/uvicorn app.main:app --port 8000` runs with canned transcripts and keyword
scenes, no API calls and no key needed. Tests: `.venv/bin/python -m pytest`.

## First run

- **Enter the stage**, then hold **Space** or the mic button and say a mood. The mic is only
  requested the first time you use it. The camera only starts when you press the camera button,
  choose a Replace/Overlay ambience, or click Reel look.
- No mic? Tap a **mood chip** (Rain, Neon, Forest, Space, Fire, Ocean). Chips use the same scene
  pipeline as a spoken cue. **Watch the demo** plays the DEMO.md cues 11 s apart with a caption;
  Stop or Esc ends it.
- Advanced controls (camera mode, calibration, looks, lyric style, stage info, latency readout,
  typed cue) live under **More**.

## Looks (presets)

| Preset | Background | Echo | Lyrics |
|---|---|---|---|
| **Reel** (default) | *Violet room*: lit wall gradient, brighter ceiling band, pink floor strip, slow breathing. Cues tint it. | *Neon contour*: **no outline is ever drawn on the performer.** Ghost and Neon contour share **one placement model** in every look and ambience (Off, Replace, Overlay, Projection): copies are past masks from the segmentation ring, drawn at identity, i.e. exactly where the subject was (no offsets, side-picking, fixed step or recentring). Only the rendering differs. Neon draws 7 outline copies; everything inside the current silhouette grown by ~4 px is erased afterwards, so only past outlines outside the body remain: a still subject leaves almost nothing, walking right leaves copies to the left along the path, an arm wave leaves arcs. **Trail source** (More > Look): *Motion only* (default) also fades the trail with a motion measure (live mask XOR the newest copy), hiding jitter slivers on a still body; *Full pose history* draws the same copies without that fade. **Spacing** (More > Look, applies to Ghost too): *Time* (default) puts copy k at k x 0.11 s ago; *Distance* takes a copy each time the subject's centre has moved at least 0.12 x its width (or 0.25 s has passed), so slow movement still shows separate copies. Pink outer, orange/yellow inner, additive glow, dimmer with age. Neon is shown in every ambience, Projection included, since it never lands on the body. Masks are smoothed (blur then re-threshold) before outlining, so contours are rounded rather than jagged (needs canvas filters: Chrome/Edge/Firefox; Safari draws the unsmoothed outline). 
| **Classic** | Moods with Muse Image backdrops | Ghost: 3 tinted copies from the same shared placement (0.11/0.22/0.33 s, or Distance spacing), drawn without glow, body cut out, then glowed, so nothing lands on or around the performer in Replace, Overlay or Projection ("Ghost echo trail" checkbox). Off mode keeps the original extras: glowing live silhouette, rising heat trail, SAM snapshots. | (same as Reel: the lyric style is its own setting) |

- **Handwritten is the default lyric style in every scene**, Reel or Classic. It is saved
  separately from the preset (More > Lyrics > Style). **Kinetic** (six scene-matched effects, with
  the Effect picker) is an option there. HUD details (cursor box, coordinates, hairlines) are on by
  default and toggleable; an older saved Classic look that forced Kinetic is migrated to Handwritten.

- Switch with the **Reel/Classic** button, the **Reel look** chip, or under More. The choice is
  saved in this browser.
- `?preset=reel` (e.g. `https://afterglow-chia.onrender.com/?preset=reel`) applies the Reel look
  and, after Enter, also starts the camera and lyrics. So does clicking Reel look. Ordinary first
  visits show the Reel visuals but start nothing.
- The look is deterministic (fixed font order, no randomness), so recordings are reproducible.
- **Lyrics are always in Latin script.** If the speech service returns Hindi in Devanagari, the
  page transliterates it to Hinglish spelling before showing it (क्या बात है → "kya baat hai",
  मैं तुमसे प्यार करता हूँ → "main tumse pyaar karta hun"). Inherent vowels follow Hindi
  pronunciation (dil, kamra, samajhna, zindagi). English words pass through unchanged. Hindi-script
  spellings of English loanwords come out approximate (ऐप → "aip").
- While the Violet room is on, cues are sent with `no_backdrop`, so the server skips Muse Image
  generation (the backdrop is hidden anyway). This saves credits and keeps the demo button cheap.
- Inspired by reference frames of a projected neon-contour performance. No artwork or text from
  them is used.

See [DEMO.md](DEMO.md) for the cue script.

## Models used (and who made them)

| Job | Model (id in `app/config.py`) | Where it runs | Maker |
|---|---|---|---|
| Speech to text (voice cues, lyrics) | Muse Voice Transcribe (`muse-voice-transcribe-1.0`) | Meta Model API | Meta |
| Cue to scene JSON | Muse Spark (`muse-spark-1.3`) | Meta Model API | Meta |
| Backdrops (8 pre-generated, new ones live in the Classic look) | Muse Image (`muse-image-1.0`) | Meta Model API | Meta |
| Snapshot silhouette every 6 s (the "afterglow" layer, Off mode) | SAM 3.1 (`sam-3.1`) | Meta Model API | Meta |
| **Live silhouette (cut-out, echo trail, Projection)** | **MediaPipe Tasks Vision selfie segmenter** | **On-device, in the browser** | **Google, not Meta** |

The live silhouette that drives the cut-out and the echo trail is Google's MediaPipe, running on
the visitor's device; no camera frames leave the browser for it. Only the slower 6 s snapshot
layer uses Meta's SAM 3.1. The ambient sound pad and the lyric transliteration are plain code, not
models.

## Ambience: Replace or Overlay

Pick **Replace** or **Overlay** with the two-option switch on the main bar (next to Mode). **Mode**
turns the chosen ambience on or off; **M** cycles Off → Replace → Overlay → Off. Choosing one turns
the camera on if it isn't. Switching between them is instant: it never restarts the camera or the
segmenter. The neon echo, lyrics and status UI draw above both. The choice and the strength are
saved in this browser; the ambience always starts Off, with no automatic camera prompt.

| Mode | What the audience sees |
|---|---|
| **Off** (default) | The original ghost echo: glowing live silhouette, a rising trail and delayed copies, plus SAM 3.1 snapshots. |
| **Replace** (cut-out) | The performer is cut out of the camera feed (mask as alpha, 2–3 px feather) and placed inside the ambience (backdrop and shader), under the lyrics. Echo trail optional (off by default, half strength). |
| **Overlay** | The live camera is the base layer (mirror respected) and the ambience is drawn on top of your real room with transparency, like a projector lighting it. **Ambience strength** (10–90%, default 55%) is in More. **Light on me** (default) lets the light fall on you too; **Keep me clear** draws you back over the ambience (85%) using the person mask so you aren't washed out. |

**Overlay blend:** `screen` reads as projected light in a dark room but turns a bright wall white;
`soft-light` keeps a bright room's detail but shows almost nothing in a dark one (black stays
black). So the page picks per room from the camera's brightness, sampled twice a second with
hysteresis: `screen` in dark rooms, `soft-light` (strength × 1.5, capped at 100%) in bright ones.
Without live camera frames (camera off or blocked), Overlay shows "Turn on the camera to overlay the
stage on your room" with a button and meanwhile looks like Replace, never a blank screen. On a
portrait phone the 16:9 camera frame sits at the bottom of the screen, as the echo does.

**Advanced: physical projector** (More > Advanced) keeps **Projection**: scenery everywhere except
a live **black** silhouette over the performer, so no light lands on them. **Grow** (0–30 px)
widens the black area; **feather** softens its edge. No echo or glow, unless **Light on performer**
is ticked: then there's no black silhouette and the neon outlines land on the body.

**Calibration** (Projection: **Calibrate** under Advanced, or press **C**): drag the 4 corner handles until the grid and
crosshairs line up with the stage (a homography), then fine-tune offset X/Y and scale, and set
mirror or flip up/down. The warp is a CSS `matrix3d` on the silhouette layer, so it adds no
per-frame cost. Settings are saved in this browser's localStorage.

## Shortcuts

Everything has an on-screen control; keys are optional. **Space** hold to speak · **L** lyrics ·
**P** camera · **M** cycle Off/Replace/Overlay · **C** calibrate (Projection) · **F** mirror · **E** Kinetic lyric effect ·
**T** latency readout · **S** ambient sound · **H** hide controls · **Esc** stop demo / close panels.

**Ambient sound** (speaker button, off by default, never saved as on): a soft Web Audio pad, with
no audio files. The scene sets its key (per style, a step higher for cold scenes) and brightness
(intensity), and it pulses gently at the scene's bpm. Use headphones or keep it low while Lyrics is
on: the mic's echo cancellation should keep the pad out of the transcript, but that wasn't tested
with real speakers.

## Latency

**Cloud pipeline**, measured by the live server on Render (`/api/health`, which keeps a median and
p90 per stage), on 2026-11-05 after the final deploy, from a session that sent recorded cues
through the real voice and lyrics paths:

| Stage (live server) | n | Median | p90 |
|---|---|---|---|
| Speech socket connect (Muse Voice Transcribe) | 12 | 671 ms | 728 ms |
| Final transcript after releasing the mic button | 8 | 142 ms | 154 ms |
| Cue to instant look (keyword scene, no model call) | 5 | 147 ms | 154 ms |
| Muse Spark call | 8 | 5.73 s | 6.49 s |
| Cue to refined scene (Spark result on screen) | 7 | 5.81 s | 6.23 s |
| Muse Image backdrop | 3 | 8.09 s | 8.09 s |
| SAM 3.1 snapshot (server round trip) | 31 | 950 ms | 1.43 s |

These are small samples from one network location; they are server-side timings and do not
include the visitor's own network.

**On-device**, measured with the on-screen readout (**T**) in the Chromium-based in-app browser on a Mac, using a **synthetic camera**
(a 640×360 canvas stream of a still photo, nudged each frame). Not measured with a real webcam.

| | Before (`stable-1100`) | After |
|---|---|---|
| Segmenter call on the main thread (inference + mask handling) | **12.2 ms** | **3.4–3.7 ms** |
| …of which mask → canvas | ~11.5 ms (full float readback + JS loop) | GPU texture, no full readback |
| Segmenter runs per camera frame | capped at ~30/s by a timer | 1 per frame (`requestVideoFrameCallback`) |
| Primary silhouette delay | drawn from the newest mask | newest mask, zero added delay |
| Echo copies delayed by | 7/14/21 frames (~0.23/0.47/0.70 s at 30 fps) | k x 0.11 s, by timestamp (Ghost 3 copies, Neon 7), shared placement |
| Per-frame allocations in the mask path | 1 canvas per frame | none (fixed 64-slot ring, ~1 s at 60 fps) |
| Camera request | 640×360 | 640×360, 60 fps ideal (24 min) |
| Draw loop in Projection (grow 8, feather 3) | n/a | 16.7 ms (holds 60 Hz) |
| Draw loop with Neon contour (Reel look), measured on the earlier outline-row version | n/a | 16.7 ms (holds 60 Hz); neon drawing ~0.4–0.5 ms on the main thread then (the current trail is the next row) |
| Neon draw cost, true-position trail (Claude desktop browser pane, page in background, synthetic 640x360 silhouette panning) | old side-row trail: ~3.3 ms (Full), ~5.9 ms (Motion only) | ~3.2 ms in either mode (one outline per snapshot, one cut-out per frame, no per-copy diffs). Real-camera fps not measured. |

What changed: segmentation is driven by `requestVideoFrameCallback` (falls back to
`requestAnimationFrame`); MediaPipe runs on its GPU delegate with its own WebGL canvas, and its mask
texture is turned into an alpha mask by one shader pass and GPU-copied into a preallocated ring. If
the GPU path fails, it falls back to reused CPU buffers.

Not measured: true camera-to-photon lag. With the synthetic camera the browser gives no
`captureTime`, so the readout's "cam→draw" figure (~17 ms) only covers frame arrival to draw, not
sensor or display latency. The segmenter's GPU time is also not captured by these main-thread
timings. Inference stays on the main thread; moving it to a worker was not attempted.

**Frame rate per ambience mode** (fake camera, in-app browser pane, 1280×720): the pane drew at
about 35 fps in *every* mode including Off (Off 28.7 ms, Replace 28.0, Overlay with Light on me 31.0,
Overlay with Keep me clear 26.9, Projection 28.4 ms per draw frame), so differences between modes
are within that pane's own frame pacing and noise, not measurable here. The main-thread JavaScript
for the camera/ambience/echo draw path measured under 0.1 ms per frame in all modes (timer
resolution). GPU compositing cost of the two blended full-screen layers was **not** measured, and no
real-camera fps was measured. The current-frame path allocates nothing per frame; the only
allocation is a 16×9 brightness sample twice a second while Overlay is on.

## Not verified

- A real webcam and a moving person. The camera numbers above, the cut-out and the echo trail were
  checked with a synthetic camera (a still photo panning or bobbing inside a canvas stream).
- Live voice and singing. Voice cues and lyrics were verified on the live site with a recorded
  spoken cue fed in as the microphone, not with someone speaking or singing live.
- Hinglish lyrics: the transliteration was tested on typed Hindi text. Whether the live speech
  service returns Hindi as Devanagari, Latin or a translation was not checked with a real voice.
- A real projector: Projection mode and calibration were checked on screen only.
- Overlay in a real room: the blend choice and the soft-light boost were tuned by eye on synthetic
  dark and bright rooms; the brightness thresholds are untuned.
- Phones and tablets: layout checked at 375 px wide in a desktop browser, not on a device.
- Safari and Firefox: `requestVideoFrameCallback`, canvas filters and the GPU mask path may behave
  differently; the fallbacks are in place but were not exercised there.
- Real frame rates with a real camera, and the GPU compositing cost of the blended layers.

## Known issues

- The camera turns off when the tab or window is hidden (by design, to save the per-visitor
  camera time). Press the camera button again after switching back.
- If MediaPipe rejects a frame timestamp (seen after quickly turning the camera off and on), the
  error is thrown inside the segmentation loop and stops it, so the mask freezes until the page is
  reloaded. Not fixed in this version.

## Next steps (not merged)

- **Song mode** (sing along to a known song, its lines shown as lyrics): branch
  `feature/song-lyrics` on GitHub.
- **Landing page**: branch `feature/landing`, local to the development machine, not pushed.
- **Audio-reactive background** (the ambience brightens with the mic level, with a strobe limit):
  branch `feature/audio-react`, local, work in progress.
- Fix the segmentation-loop timestamp issue above, and move inference to a worker.
- Test with real webcams, live voices, phones, Safari and Firefox, and a real projector.
