"use strict";
// Song mode (experimental). Everything client-side for it lives in this file so rebasing onto main
// touches index.html in only three one-line hooks:
//   hello:     songHello(m)           ws message "song"/"song_line": songMessage(m)      onLyric: songActive()
// The server (app/song_controller.py) identifies the song, follows it, and sends only the current and
// next line. They are shown with the existing handwritten renderer (handLyric / #hand).
const song = { enabled: false, on: false, locked: false, title: "", artist: "", cur: "", next: "", poll: null };

function songHello(m) {
  song.enabled = !!m.song_mode;
  const box = document.getElementById("songBox");
  if (box) box.hidden = !song.enabled;
}

function songActive() { return song.locked; }       // while true, live lyric events are ignored

function songBuildUI() {
  const more = document.getElementById("more");
  if (!more || document.getElementById("songBox")) return;
  const box = document.createElement("div");
  box.id = "songBox"; box.hidden = true;
  box.innerHTML = `<h3>Song mode (experimental)</h3>
    <label><input type="checkbox" id="songToggle"> Follow the song playing nearby</label>
    <div id="songInfo" aria-live="polite" style="font-size:12px;color:var(--ui-dim);min-height:1.4em"></div>
    <div id="songCredit" style="font-size:11px;color:var(--ui-dim)" hidden>lyrics via LRCLIB (community database)</div>`;
  const heading = [...more.querySelectorAll("h3")].find(x => x.textContent.trim() === "Show");
  more.insertBefore(box, heading || null);                                       // its own section, above "Show"
  const nxt = document.createElement("div");
  nxt.id = "songNext"; nxt.className = "f0";
  nxt.style.cssText = "position:absolute;left:0;top:100%;width:100%;margin-top:.15em;font-size:.62em;line-height:1.2;"
    + "color:rgba(255,244,255,.5);text-shadow:0 0 10px rgba(231,77,158,.25);transition:opacity .3s;opacity:0;pointer-events:none";
  document.getElementById("hand").appendChild(nxt);
  document.getElementById("songToggle").addEventListener("change", e => songToggle(e.target.checked));
}

function songInfo(text, credit) {
  const i = document.getElementById("songInfo"); if (i) i.textContent = text || "";
  const c = document.getElementById("songCredit"); if (c) c.hidden = !credit;
}

function songToggle(on) {
  clearInterval(song.poll);
  song.on = on;
  const cb = document.getElementById("songToggle"); if (cb) cb.checked = on;
  if (!on) { wsSend(JSON.stringify({ type: "song_stop" })); songEnd(); songInfo(""); return; }
  songInfo("Turning lyrics on…");
  if (!ly.on && !ly.pending) lyricsOn();          // Song mode rides on the live lyrics stream
  let waited = 0;
  song.poll = setInterval(() => {                 // wait for the lyrics stream, then start following
    waited += 200;
    if (ly.on) { clearInterval(song.poll); wsSend(JSON.stringify({ type: "song_start" })); }
    else if (waited > 6000) { clearInterval(song.poll); songToggle(false); setStatus("error", "Song mode needs Lyrics (and the mic). Turn Lyrics on first."); }
  }, 200);
}

function songEnd() {                              // back to plain live lyrics
  song.locked = false; song.cur = song.next = "";
  const n = document.getElementById("songNext"); if (n) n.style.opacity = 0;
  hand.ended = true;                              // the next live phrase starts a fresh line
  if (typeof lookChanged === "function") lookChanged();   // restore the look's own lyric element
}

function songShow(cur, next) {
  const hd = document.getElementById("hand");
  hd.style.display = ""; document.getElementById("lyrics").style.display = "none";   // song lines always use the handwritten style
  hand.offset = 0; hand.ended = true;             // each song line is its own phrase: crossfade the old one out
  handLyric(toLatin(cur), true);                  // existing renderer: letter by letter, follows the subject
  const n = document.getElementById("songNext");
  if (n) { n.textContent = toLatin(next || ""); n.style.opacity = next ? 1 : 0; }
}

function songMessage(m) {
  if (m.type === "song_line") {
    if (!song.on || !song.locked) return;
    song.cur = m.cur; song.next = m.next;
    songShow(m.cur, m.next);
    return;
  }
  switch (m.state) {
    case "listening":
      songInfo("Listening for a song…"); setStatus("thinking", "Listening for a song…"); break;
    case "found":
      if (!song.on) return;
      song.locked = true; song.title = m.title; song.artist = m.artist;
      songInfo(`${m.title} · ${m.artist}`, true); setStatus("ready", `Found: ${m.title} by ${m.artist}`); break;
    case "none":
      songEnd(); songInfo("No song matched");
      setStatus("limited", m.reason === "budget" ? "Live budget used up, showing live lyrics" : "Couldn't match a song, showing live lyrics"); break;
    case "lost":
      songEnd(); songInfo("Lost the song, listening again…");
      setStatus("limited", "Lost the song, showing live lyrics"); break;
    case "off":
      songToggle(false); setStatus("error", m.detail || "Song mode isn't available"); break;
  }
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", songBuildUI); else songBuildUI();
