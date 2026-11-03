"""Structured per-stage latency logging: one JSON line per stage on stdout."""

from __future__ import annotations

import json
import logging
import statistics
import sys
import time
from collections import defaultdict, deque
from contextlib import contextmanager

_log = logging.getLogger("afterglow")
if not _log.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(h)
    _log.setLevel(logging.INFO)

_recent: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))
_fails: dict[str, int] = defaultdict(int)


def log_stage(stage: str, ms: float | None, ok: bool, backend: str, **extra) -> None:
    rec = {"ts": round(time.time(), 3), "stage": stage, "ms": None if ms is None else round(ms, 1),
           "ok": ok, "backend": backend, **extra}
    if ok and ms is not None:
        _recent[stage].append(ms)
    elif not ok:
        _fails[stage] += 1
    _log.info(json.dumps(rec, default=str))


def log_event(event: str, **extra) -> None:
    _log.info(json.dumps({"ts": round(time.time(), 3), "event": event, **extra}, default=str))


@contextmanager
def timed(stage: str, backend: str, **extra):
    t0 = time.perf_counter()
    state = {"ok": True}
    try:
        yield state
    except BaseException:
        state["ok"] = False
        raise
    finally:
        log_stage(stage, (time.perf_counter() - t0) * 1000, state["ok"], backend, **extra)


def summary() -> dict:
    out = {}
    for stage, vals in _recent.items():
        v = sorted(vals)
        out[stage] = {"n": len(v), "median_ms": round(statistics.median(v), 1),
                      "p90_ms": round(v[int(0.9 * (len(v) - 1))], 1), "max_ms": round(v[-1], 1),
                      "fails": _fails.get(stage, 0)}
    for stage, n in _fails.items():
        out.setdefault(stage, {"n": 0, "fails": n})
    return out
