"""SAM 3.1 output -> the performer's mask, for the browser to draw.

SAM returns special-token text: per object a pixel box and a base85 one_bit raster that
covers exactly that box. The official Python parser decodes and verifies every mask while
parsing, which takes seconds on a small server CPU, so here we only extract the tokens and
let the browser decode with Meta's JS parser (which validates the payload). The PNG path,
decoded here with meta_sam_parser, is a fallback for clients that can't load the JS parser.
"""

from __future__ import annotations

import base64
import io
import re
import time

from meta_sam_parser import decode_mask_to_raster
from meta_sam_parser._types import SegmentationMask
from PIL import Image

_TO_ALPHA = bytes([0, 255]) + bytes(254)  # raster bytes are 0/1


def mask_png(raster: bytes, width: int, height: int) -> bytes:
    alpha = Image.frombytes("L", (width, height), raster.translate(_TO_ALPHA))
    la = Image.merge("LA", (Image.new("L", (width, height), 255), alpha))
    out = io.BytesIO()
    la.save(out, "PNG", compress_level=6)
    return out.getvalue()


# Record grammar, as documented in meta_sam_parser/_segmentation.py: a line is a frame header
# <Nf> followed by records "id<|box;...|><|mask;...;data=H,W,<enc>payload|>". The payload
# alphabet never contains "|" or ";", so a token always ends at the first "|>".
_LINE = re.compile(r"^<([0-9]+)f(?:;[^>]*)?>(.*)$")
_RECORD = re.compile(r"([0-9]+)((?:<\|[A-Za-z][A-Za-z0-9_.-]*(?:;[^|]*)?\|>)+)")
_TOKEN = re.compile(r"<\|([A-Za-z][A-Za-z0-9_.-]*)(?:;([^|]*))?\|>")
_MASK_DATA = re.compile(r"^([0-9]+),([0-9]+),([!~][^|]+)$")
_ENCODING = {"!": "one_bit", "~": "lossless"}


def _fields(body: str | None) -> dict[str, str]:
    return dict(kv.split("=", 1) for kv in (body or "").split(";") if "=" in kv)


def extract_records(text: str) -> list[dict]:
    """Box + raw mask per object, without decoding. Malformed records are skipped."""
    out = []
    for line in text.splitlines():
        lm = _LINE.match(line.strip())
        if not lm:
            continue
        for rm in _RECORD.finditer(lm.group(2)):
            tokens = {t.group(1): _fields(t.group(2)) for t in _TOKEN.finditer(rm.group(2))}
            box, mask = tokens.get("box"), tokens.get("mask")
            md = _MASK_DATA.match((mask or {}).get("data", ""))
            if not box or not md:
                continue
            try:
                h, w = int(md.group(1)), int(md.group(2))
                left = float(box["x1"]) + float(mask.get("x", 0))
                top = float(box["y1"]) + float(mask.get("y", 0))
                conf = mask.get("c", box.get("c"))
                out.append({"id": rm.group(1), "bounds": [left, top, left + w, top + h],
                            "confidence": None if conf is None else float(conf),
                            "mask": {"encoding": _ENCODING[md.group(3)[0]], "payload": md.group(3),
                                     "width": w, "height": h}})
            except (KeyError, ValueError):
                continue
    return out


def main_subject(text: str, frame_w: int, frame_h: int, as_png: bool = False) -> dict | None:
    """The main subject's mask, or None for zero matches. Main subject = largest box weighted
    by confidence (the performer is usually the biggest person in frame)."""
    records = extract_records(text)
    if not records:
        return None

    def score(r) -> float:
        x1, y1, x2, y2 = r["bounds"]
        return (x2 - x1) * (y2 - y1) * (r["confidence"] or 1.0)

    r = max(records, key=score)
    out = {"bounds": r["bounds"], "frame": [frame_w, frame_h], "confidence": r["confidence"],
           "objects": len(records), "raster": [r["mask"]["width"], r["mask"]["height"]]}
    if not as_png:
        out["mask"] = r["mask"]
        return out
    t0 = time.perf_counter()
    raster = decode_mask_to_raster(SegmentationMask(**r["mask"]))
    out["decode_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["png"] = base64.b64encode(mask_png(raster, r["mask"]["width"], r["mask"]["height"])).decode()
    return out


def jpeg_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        if im.format != "JPEG":
            raise ValueError("not a JPEG")
        return im.size
