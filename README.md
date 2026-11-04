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
  choose a Mode, or click Reel look.
- No mic? Tap a **mood chip** (Rain, Neon, Forest, Space, Fire, Ocean). Chips use the same scene
  pipeline as a spoken cue. **Watch the demo** plays the DEMO.md cues 11 s apart with a caption;
  Stop or Esc ends it.
- Advanced controls (camera mode, calibration, looks, lyric style, stage info, latency readout,
  typed cue) live under **More**.

## Looks (presets)

| Preset | Background | Echo | Lyrics |
|---|---|---|---|
| **Reel** (default) | *Violet room*: lit wall gradient, brighter ceiling band, pink floor strip, slow breathing. Cues tint it. | *Neon contour*: a live outline (no added delay) plus a motion trail. Past outlines from the last ~0.7 s (every 110 ms) are drawn where each person actually was, and anything inside where they are now is cut away. So a still person has no trail, a moving person leaves copies along their path, and each person in frame gets their own trail. Pink outer, orange/yellow inner, additive glow, older copies dimmer. | *Handwritten*: up to 2 lines, revealed letter by letter, one line above the performer's head (with several people in frame, the highest head) with an eased follow. Each phrase uses the next font in a fixed order (Caveat, Gaegu, Shadows Into Light, Reenie Beanie, Fraunces). Optional HUD details: cursor box, x/y readout, hairline leader lines. |
| **Classic** | Moods with Muse Image backdrops | Ghost (difference-blend silhouette, trail, delayed copies) | Kinetic type, 6 effects |

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

## Performance modes

Switch with the **Mode** button, or press **M** (Off → Composite → Projection). Choosing a mode
turns the camera on. The echo style (Neon contour or Ghost) comes from the current look.

| Mode | What the audience sees |
|---|---|
| **Off** (default) | The original ghost echo: glowing live silhouette, a rising trail and delayed copies, plus SAM 3.1 snapshots. |
| **Composite** | The live webcam with the background removed (mask as alpha, 2–3 px feather) over the backdrop and shader, under the lyrics. Echo trail optional (off by default, drawn at half strength). |
| **Projection** | For a projector pointed at the performer: scenery everywhere except a live **black** silhouette over the performer, so no light lands on them. **Grow** (0–30 px) widens the black area; **feather** softens its edge. No echo or glow, unless **Light on performer** is ticked (More): then there's no black silhouette and the neon outlines land on the body. |

**Calibration** (Projection mode, press **C**): drag the 4 corner handles until the grid and
crosshairs line up with the stage (a homography), then fine-tune offset X/Y and scale, and set
mirror or flip up/down. The warp is a CSS `matrix3d` on the silhouette layer, so it adds no
per-frame cost. Settings are saved in this browser's localStorage.

## Shortcuts

Everything has an on-screen control; keys are optional. **Space** hold to speak · **L** lyrics ·
**P** camera · **M** mode · **C** calibrate · **F** mirror · **E** kinetic lyric effect ·
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
| Echo copies delayed by | 7/14/21 frames (~0.23/0.47/0.70 s at 30 fps) | 0.10/0.22/0.38 s, by timestamp |
| Per-frame allocations in the mask path | 1 canvas per frame | none (fixed 40-slot ring) |
| Camera request | 640×360 | 640×360, 60 fps ideal (24 min) |
| Draw loop in Projection (grow 8, feather 3) | n/a | 16.7 ms (holds 60 Hz) |
| Draw loop with Neon contour (Reel look) | n/a | 16.7 ms (holds 60 Hz); neon drawing ~0.4–0.5 ms on the main thread |

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
- Singing or speech accuracy of the handwritten lyrics: tested by feeding words to the page,
  not with a live voice (no mic in the test browser).
- Hinglish lyrics: the transliteration was tested on typed Hindi text. Whether the live speech
  service returns Hindi as Devanagari, Latin or a translation, with `languageBias: ["English"]`,
  was not checked with a real voice.
- Head-following and the pose-history row were checked with a synthetic subject (a photo panning
  over a plain wall), not a moving person.
- Safari and Firefox: `requestVideoFrameCallback`, canvas `filter` (feather) and the GPU mask
  path may behave differently; the fallbacks are in place but were not exercised there.

## Song mode (experimental, branch only)

Branch `feature/song-lyrics`; not merged to `main` and not deployed. While **Lyrics** is on and a
song is playing near the mic, Song mode tries to recognise the song from the words the speech
service transcribes, fetches time-synced lyrics, follows the song's position, and shows the
current line (and the next one, dimmer) in the handwritten lyric style, including Follow subject.

**Turn it on:** run the server with `SONG_MODE=1`; then tick **Song mode** in More (off by
default, and ignored by the server unless the flag is set). It turns Lyrics on for you.

**How it works**
1. **Identify (server):** the last ~15 s of final transcript go to Muse Spark (`muse-spark-1.3`)
   with a strict JSON schema `{title, artist, confidence}`. Spark is told never to output lyrics,
   and anything that isn't a valid title/artist with confidence ≥ 0.4 counts as "not recognised".
   One try per 20 s while unmatched, at most 4 per session, charged to the daily budget and
   limited per IP.
2. **Look up:** [LRCLIB](https://lrclib.net) (no key; the request carries only a descriptive
   User-Agent) is searched by title/artist for synced lyrics. The candidate is accepted only if
   the heard words fuzzy-match its lyric lines (mean similarity ≥ 0.55); otherwise it is treated
   as not recognised. Results are cached in memory for the session.
3. **Follow:** each time the latest heard words match a lyric line, the song clock locks to that
   line's timestamp and then runs locally, re-syncing on every confident match (drift correction;
   with repeated choruses the match nearest the predicted position wins). If nothing matches for
   15 s the page falls back to plain live lyrics and listens again.
4. **Show:** only the current and next line are sent to the browser. Status text: "Listening for
   a song…", "Found: <title> by <artist>", "Couldn't match a song, showing live lyrics".

**Honest limits**
- Works only for songs with clear vocals that Spark recognises *from the words*; there is no
  audio fingerprinting. Instrumental or heavily processed tracks won't match.
- The lyric text comes from a community database (LRCLIB), **not from Meta**. The match can be
  wrong; accuracy depends on the room, the music level and the speech service.
- Lyrics are held in memory only for the session: never written to disk, logged or committed.
  Tests and the MOCK mode use an invented placeholder song, not real lyrics.
- If lyrics licensing is a concern for a public deployment, keep Song mode off (the default).
- Not yet verified: a real song through a real mic, LRCLIB reachability from Render, latency, and
  Spark's recognition rate.

**MOCK mode:** with `MOCK=1 SONG_MODE=1`, the offline singer performs an invented song
("Placeholder Song"), so the whole flow (listening → found → lines advancing → fallback) runs with
no network. `static/song.js` holds all the client code for it.
