"""SAM 3.1 output -> one performer mask as a small PNG the browser can draw.

SAM returns special-token text: per object a pixel box and a base85 one_bit raster that
covers exactly that box (half-open source-pixel bounds). We pick the main subject, decode
its raster with the official meta_sam_parser, and encode it as an LA PNG (white + alpha).
"""

from __future__ import annotations

import base64
import io
import time

from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format
from PIL import Image

_TO_ALPHA = bytes([0, 255]) + bytes(254)  # raster bytes are 0/1


def mask_png(raster: bytes, width: int, height: int) -> bytes:
    alpha = Image.frombytes("L", (width, height), raster.translate(_TO_ALPHA))
    la = Image.merge("LA", (Image.new("L", (width, height), 255), alpha))
    out = io.BytesIO()
    la.save(out, "PNG", compress_level=6)
    return out.getvalue()


def main_subject(text: str, frame_w: int, frame_h: int, as_png: bool = False) -> dict | None:
    """Parse SAM output text and return the main subject's mask, or None for zero matches.

    Main subject = largest box weighted by confidence (the performer is usually the
    biggest person in frame). By default the compact wire mask is returned for the browser
    to decode (pure-Python decoding takes seconds on a small server CPU); as_png=True
    decodes here instead, for clients that can't load the JS decoder."""
    if not text.strip():
        return None
    parser = image_segmentation_format().create_parser()
    parser.push(text, emit=False)
    result = parser.finish(CompletedOutcome()).result
    masks = [r for r in result.records if r.kind == "mask"]
    if not masks:
        return None

    def score(m) -> float:
        b = m.bounds
        return max(0.0, b.right - b.left) * max(0.0, b.bottom - b.top) * (m.confidence or 1.0)

    m = max(masks, key=score)
    b = m.bounds
    out = {
        "bounds": [b.left, b.top, b.right, b.bottom],
        "frame": [frame_w, frame_h],
        "confidence": m.confidence,
        "objects": len(masks),
        "raster": [m.mask.width, m.mask.height],
    }
    if not as_png:
        out["mask"] = {"encoding": m.mask.encoding, "payload": m.mask.payload,
                       "width": m.mask.width, "height": m.mask.height}
        return out
    t0 = time.perf_counter()
    raster = decode_mask_to_raster(m.mask)
    out["decode_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["png"] = base64.b64encode(mask_png(raster, m.mask.width, m.mask.height)).decode()
    return out


def jpeg_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        if im.format != "JPEG":
            raise ValueError("not a JPEG")
        return im.size
