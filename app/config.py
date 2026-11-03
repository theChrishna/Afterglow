"""Runtime configuration. The API key is read here and nowhere else; it is never logged."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
BANK_DIR = STATIC_DIR / "backdrops"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _key() -> str | None:
    k = os.environ.get("MODEL_API_KEY", "").strip()
    return None if not k or k.endswith("your_key_here") else k


MODEL_API_KEY = _key()
MOCK = os.environ.get("MOCK", "0") == "1" or MODEL_API_KEY is None

BASE_URL = "https://api.meta.ai/v1"
ASR_WS_URL = "wss://api.meta.ai/v1/asr/realtime"

ASR_MODEL = "muse-voice-transcribe-1.0"
SPARK_MODEL = "muse-spark-1.3"
IMAGE_MODEL = "muse-image-1.0"
SAM_MODEL = "sam-3.1"

# Documented list prices (dev.meta.ai/docs/pricing-rate-limits), used for the spend guard.
PRICE_ASR_PER_SEC = 0.18 / 3600
PRICE_SPARK_IN = 1.25 / 1_000_000
PRICE_SPARK_OUT = 4.25 / 1_000_000
PRICE_IMAGE = 0.01
PRICE_SAM = 2.50 / 1000

DAILY_BUDGET_USD = float(os.environ.get("DAILY_BUDGET_USD", "5"))

# Per-IP limits: (capacity, refill seconds per token)
LIMIT_CUES = (6, 10.0)        # 6 burst, then 1 per 10 s
LIMIT_IMAGES = (1, 60.0)      # 1 per minute
LIMIT_SAM = (1, 3.0)          # 1 per 3 s
PERFORM_SECONDS_PER_IP = int(os.environ.get("PERFORM_SECONDS_PER_IP", "180"))

# Timeouts (s)
TIMEOUT_ASR_CONNECT = 6
TIMEOUT_ASR_FINAL = 8
TIMEOUT_SPARK = 10
TIMEOUT_IMAGE = 45
TIMEOUT_SAM = 15

# PTT strategy: "buffered" = connect on press and buffer audio until ack;
# "spare" = keep one pre-connected session alive with silence (fallback).
ASR_STRATEGY = os.environ.get("ASR_STRATEGY", "buffered")
