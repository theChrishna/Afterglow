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

_TBD: Off / Composite / Projection (filled in when built)._

## Latency

_TBD: measured table, fake camera only (filled in after measuring)._

## Not verified

_TBD._
