"""Generate the backdrop bank (one image per mood in app/scene.py BANK) with Muse Image.

Writes static/backdrops/<id>.webp (1280x720, ~40-80 KB). Skips files that already exist
unless --force. Cost: $0.01 per image (documented list price).

    .venv/bin/python scripts/pregen_backdrops.py [--force] [--only rain_city,neon_synth]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.backends.meta_api import MetaImageModel  # noqa: E402
from app.scene import BANK  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    if config.MOCK:
        print("MOCK is on or MODEL_API_KEY is missing; nothing generated.")
        return 1

    wanted = [b for b in BANK if not args.only or b in args.only.split(",")]
    todo = [b for b in wanted if args.force or not (config.BANK_DIR / f"{b}.webp").exists()]
    print(f"{len(todo)} to generate (~${0.01 * len(todo):.2f}); {len(wanted) - len(todo)} already present")
    model, sem = MetaImageModel(), asyncio.Semaphore(4)

    async def one(bid: str) -> bool:
        async with sem:
            t0 = time.perf_counter()
            try:
                data = await model.generate(BANK[bid]["prompt"])
            except Exception as e:  # report and keep going
                print(f"  {bid}: FAILED {e}")
                return False
            (config.BANK_DIR / f"{bid}.webp").write_bytes(data)
            print(f"  {bid}: {len(data) // 1024} KB in {time.perf_counter() - t0:.1f}s")
            return True

    ok = await asyncio.gather(*(one(b) for b in todo))
    return 0 if all(ok) else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
