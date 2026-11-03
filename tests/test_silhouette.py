import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.limits import limits
from app.main import app
from app.sam_mask import mask_png


def _jpeg(w=640, h=360) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (40, 40, 40)).save(buf, "JPEG")
    return buf.getvalue()


def test_mock_silhouette_then_rate_limited():
    with TestClient(app) as c:
        hdr = {"Content-Type": "image/jpeg", "x-forwarded-for": "10.0.0.1"}
        r = c.post("/api/silhouette", content=_jpeg(), headers=hdr)
        assert r.status_code == 200
        m = r.json()["mask"]
        assert m["frame"] == [640, 360] and len(m["bounds"]) == 4
        assert m["mask"]["encoding"] == "one_bit" and m["mask"]["payload"].startswith("!")
        r2 = c.post("/api/silhouette", content=_jpeg(), headers=hdr)
        assert r2.status_code == 429 and r2.json()["error"] == "too_fast"


def test_png_fallback_format():
    with TestClient(app) as c:
        r = c.post("/api/silhouette", content=_jpeg(),
                   headers={"Content-Type": "image/jpeg", "x-forwarded-for": "10.0.0.4", "x-mask-format": "png"})
        m = r.json()["mask"]
        assert Image.open(io.BytesIO(base64.b64decode(m["png"]))).mode == "LA" and "mask" not in m


def test_mock_wire_mask_decodes_like_sam():
    import asyncio
    from meta_sam_parser import decode_mask_to_raster
    from meta_sam_parser._types import SegmentationMask
    from app.backends.mock import MockSegmenter
    out = asyncio.run(MockSegmenter().segment(_jpeg(), 640, 360))
    mk = out["mask"]
    raster = decode_mask_to_raster(SegmentationMask(encoding="one_bit", payload=mk["payload"],
                                                    width=mk["width"], height=mk["height"]))
    assert len(raster) == mk["width"] * mk["height"] and 0 < sum(raster) < len(raster)


def test_rejects_non_jpeg():
    with TestClient(app) as c:
        r = c.post("/api/silhouette", content=b"not an image", headers={"x-forwarded-for": "10.0.0.2"})
        assert r.status_code == 400


def test_perform_time_cap(monkeypatch):
    monkeypatch.setattr(limits, "perform_seconds", 0)
    with TestClient(app) as c:
        r = c.post("/api/silhouette", content=_jpeg(), headers={"x-forwarded-for": "10.0.0.3"})
        assert r.status_code == 429 and r.json()["error"] == "perform_time_up"


def test_mask_png_alpha_matches_raster():
    raster = bytes([0, 1, 1, 0, 1, 0])
    im = Image.open(io.BytesIO(mask_png(raster, 3, 2)))
    assert list(im.getchannel("A").getdata()) == [0, 255, 255, 0, 255, 0]
