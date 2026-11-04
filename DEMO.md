# Afterglow demo script

Rehearsed cues for a 2–3 minute live demo. Each cue hits a different pre-generated backdrop, so the
stage changes visibly even if image generation is slow. Hold **Space** (or the on-screen button),
say the cue, and release.

| # | Say this | Instant reaction (~0.5 s) | Then (~5 s, Muse Spark) | Backdrop |
|---|---|---|---|---|
| 1 | "Make it feel like a rainy city at 3am" | cold blue light, rain streaks + bokeh | Spark's own palette and grain | `rain_city`, new image ~12 s later |
| 2 | "Switch background mood to warm retro synth neon" | magenta/orange synth grid, 108 bpm pulse | refined palette and tempo | `neon_synth` |
| 3 | "Take us into deep space, slow and floating" | nebula clouds and stars, slow motion | | `deep_space` |
| 4 | "Misty forest at dawn, very calm" | soft green fog, light shafts | | `forest_mist` |
| 5 | "Now set everything on fire, fast and loud" | rising embers, 140 bpm strobe pulse | | `ember_storm` |
| 6 | "Cold arctic night with the northern lights" | aurora curtains, icy tint | | `arctic_aurora` |
| 7 | "Brighter, and a bit faster" | (relative cue: no instant jump) | Spark adjusts the current scene | stays |
| 8 | "Drop us underwater, calm and blue" | caustic light, slow | | `ocean_calm` |

Cue 7 shows that Spark reads the current scene: it changes brightness and speed instead of
replacing the mood.

## Run of show

1. Open the stage URL a few minutes early (the free Render instance sleeps when idle). For the
   recorded look use `https://afterglow-chia.onrender.com/?preset=reel` (Reel look: Violet room,
   Neon contour, handwritten lyrics). Click **Enter the stage** and allow the camera and mic.
2. Say cue 1. Point out: the caption appears while you speak, the light reacts at once, the
   refined scene lands a few seconds later, and a freshly generated backdrop crossfades in after
   ~12 s.
3. Run cues 2–6 back to back, leaving ~8 s between them.
4. Cue 7 (relative change), then cue 8.
5. Press **H** to hide the controls for a clean final look.

No mic? Tap the mood chips (Rain, Neon, Forest, Space, Fire, Ocean). Or press **Watch the demo**,
which plays cues 1–8 here, 11 s apart, with a caption (Stop or Esc ends it).

## Looks

- **Reel** (default; the **Reel look** chip, the Reel/Classic button, or `?preset=reel`): Violet room,
  Neon contour trail (no outline on you; copies stay at the places you have just been, so walking right leaves outlines behind you on the left and a still pose leaves none; More > Look > Trail source: Motion only / Full pose history, Spacing: Time / Distance), handwritten lyrics above your head. Deterministic, so takes are
  reproducible. Backdrops are hidden and not generated.
- **Classic**: moods with Muse Image backdrops, ghost echo.
- Lyrics are **handwritten** in every scene (More > Lyrics > Style switches to Kinetic).

## Ambience (camera)

- The **Replace | Overlay** switch sits next to **Mode**. **Replace** cuts you out of the camera and
  puts you inside the ambience. **Overlay** shows the live camera and projects the ambience over your
  real room (strength slider and Keep me clear / Light on me under More). **Mode** turns it on and
  off; **M** cycles Off → Replace → Overlay.
- Overlay needs the camera: without it the page shows a prompt and looks like Replace meanwhile.
- **More > Advanced: physical projector** has Projection (a black cut-out so a real projector doesn't
  light you); press **C** to calibrate: drag the 4 corners onto the stage, then adjust offset and scale.
- **F** mirror, **T** latency readout, **L** lyrics, **P** camera, **S** ambient sound (off by default), **H** hide controls, **Esc** stop the demo.

## If something goes wrong

- **Mic fails or the room is noisy:** tap a mood chip, or type the cue under **More** and press Enter. Same pipeline,
  minus speech recognition.
- **Status pill says "Something slipped":** the last scene stays up; just give the next cue.
- **Network is down:** run locally with `MOCK=1` (canned transcripts and keyword scenes, no API
  calls), or play the fallback recording.
- **"Give it a few seconds":** the per-IP limit is 6 quick cues, then one every 10 s.
