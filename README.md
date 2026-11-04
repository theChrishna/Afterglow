# Afterglow

A live-performance stage engine. Say a mood and the stage becomes it: the performer speaks cues
(push-to-talk) or taps a mood chip, light and motion change at once, and the refined scene lands a
few seconds later. With the camera on, the performer's silhouette echoes on the stage, and what
they say or sing appears as lyrics.

Live: https://afterglow-chia.onrender.com (Render free plan; the first load after idle is slow)

*Built during the hackathon.*

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

| Job | Model | Where it runs | Maker |
|---|---|---|---|
| Speech to text (commands, lyrics) | Muse Voice Transcribe | Meta Model API | Meta |
| Cue to scene JSON | Muse Spark | Meta Model API | Meta |
| Backdrops (8 pre-generated, new ones live) | Muse Image | Meta Model API | Meta |
| Snapshot silhouette every 6 s ("afterglow" layer) | SAM 3.1 | Meta Model API | Meta |
| **Real-time silhouette (echo, modes)** | **MediaPipe selfie segmenter** | **On-device, in the browser** | **Google, not Meta** |

The real-time silhouette is a Google on-device model. Only the slower 6 s snapshot layer uses
Meta's SAM 3.1.

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

Measured with the on-screen readout (**T**) in the Chromium-based in-app browser on a Mac, using a **synthetic camera**
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
| Draw loop with Neon contour (Reel look) | n/a | 16.7 ms (holds 60 Hz); neon drawing ~0.4–0.5 ms on the main thread |
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

- A real webcam (all numbers above use a synthetic canvas camera).
- A real projector: Projection mode and calibration were checked on screen only.
- Overlay on a real camera and in a real room: the blend choice and the 1.5× soft-light boost were
  tuned by eye on a synthetic dark room and a bright room (a photo on flat colour), not on real
  rooms, projectors or webcams; the brightness thresholds (0.5 up, 0.38 down) are untuned.
- Phones and tablets: layout checked at 375 px wide in a desktop browser, not on a device.
- Singing or speech accuracy of the handwritten lyrics: tested by feeding words to the page,
  not with a live voice (no mic in the test browser).
- Hinglish lyrics: the transliteration was tested on typed Hindi text. Whether the live speech
  service returns Hindi as Devanagari, Latin or a translation, with `languageBias: ["English"]`,
  was not checked with a real voice.
- Head-following and the pose-history row were checked with a synthetic subject (a photo panning
  over a plain wall), not a moving person.
- Safari and Firefox: `requestVideoFrameCallback`, canvas `filter` (feather) and the GPU mask
  path may behave differently; the fallbacks are in place but were not exercised there.
