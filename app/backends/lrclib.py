"""LRCLIB client (https://lrclib.net): community-run database of synced lyrics. No API key.

Lyric text is only held in memory for the session. It is never written to disk or logged.
"""

from __future__ import annotations

import time

import httpx

from .. import config
from ..song import norm, parse_lrc, similarity
from ..telemetry import log_stage

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=config.LRCLIB_BASE,
            headers={"User-Agent": config.LRCLIB_UA},      # the only identifying header we send
            timeout=httpx.Timeout(config.TIMEOUT_LRCLIB, connect=4.0),
        )
    return _client


class LRCLibSource:
    name = "lrclib"

    def __init__(self, http: httpx.AsyncClient | None = None):
        self._http = http

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http or client()

    async def find(self, title: str, artist: str) -> list[tuple[float, str]] | None:
        t0 = time.perf_counter()
        try:
            r = await self.http.get("/api/search", params={"track_name": title, "artist_name": artist})
            if r.status_code != 200:
                log_stage("lrclib", (time.perf_counter() - t0) * 1000, False, self.name, error=f"HTTP {r.status_code}")
                return None
            items = r.json()
        except (httpx.HTTPError, ValueError) as e:
            log_stage("lrclib", (time.perf_counter() - t0) * 1000, False, self.name, error=type(e).__name__)
            return None
        best, best_score = None, 0.0
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict) or not isinstance(it.get("syncedLyrics"), str) or not it["syncedLyrics"]:
                continue
            score = similarity(str(it.get("trackName", "")), title) + 0.5 * similarity(str(it.get("artistName", "")), artist)
            if score > best_score:
                best, best_score = it, score
        lrc = parse_lrc(best["syncedLyrics"]) if best else []
        log_stage("lrclib", (time.perf_counter() - t0) * 1000, bool(lrc), self.name, candidates=len(items) if isinstance(items, list) else 0)
        return lrc or None
