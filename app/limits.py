"""Per-IP token buckets, per-IP Perform-mode time, and a global daily USD budget.

All in memory: fine for a single server instance. A restart resets counters.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from . import config


class TokenBucket:
    def __init__(self, capacity: int, refill_s: float):
        self.capacity, self.refill_s = capacity, refill_s
        self.tokens, self.t = float(capacity), time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.t) / self.refill_s)
        self.t = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class Limits:
    KINDS = {"cue": config.LIMIT_CUES, "image": config.LIMIT_IMAGES, "sam": config.LIMIT_SAM}

    def __init__(self, daily_budget: float = config.DAILY_BUDGET_USD,
                 perform_seconds: int = config.PERFORM_SECONDS_PER_IP):
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self.daily_budget = daily_budget
        self.perform_seconds = perform_seconds
        self._day = self._today()
        self._spent = 0.0
        self._calls: dict[str, int] = {}
        self._perform_start: dict[str, float] = {}

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _roll(self) -> None:
        d = self._today()
        if d != self._day:
            self._day, self._spent, self._calls, self._perform_start = d, 0.0, {}, {}

    def allow(self, ip: str, kind: str) -> bool:
        with self._lock:
            b = self._buckets.get((ip, kind))
            if b is None:
                b = self._buckets[(ip, kind)] = TokenBucket(*self.KINDS[kind])
            return b.take()

    def can_spend(self, est_usd: float) -> bool:
        with self._lock:
            self._roll()
            return self._spent + est_usd <= self.daily_budget

    def charge(self, kind: str, usd: float) -> None:
        with self._lock:
            self._roll()
            self._spent += usd
            self._calls[kind] = self._calls.get(kind, 0) + 1

    def perform_remaining(self, ip: str) -> float:
        """Seconds of Perform mode left for this IP today (clock starts at first SAM call)."""
        with self._lock:
            self._roll()
            start = self._perform_start.get(ip)
            if start is None:
                return float(self.perform_seconds)
            return max(0.0, self.perform_seconds - (time.monotonic() - start))

    def start_perform(self, ip: str) -> None:
        with self._lock:
            self._roll()
            self._perform_start.setdefault(ip, time.monotonic())

    def status(self) -> dict:
        with self._lock:
            self._roll()
            return {"day_utc": self._day, "spent_usd": round(self._spent, 4),
                    "budget_usd": self.daily_budget,
                    "remaining_usd": round(max(0.0, self.daily_budget - self._spent), 4),
                    "calls": dict(self._calls)}


limits = Limits()
