"""Backend selection: live Meta API unless MOCK=1, no key, or the daily budget is spent."""

from __future__ import annotations

from .. import config
from .base import BackendError, PartialCallback  # noqa: F401
from .mock import MockASRSession, MockImageModel, MockSceneModel

_live_scene = None
_live_image = None


def asr_session(on_partial: PartialCallback | None, live: bool):
    if live and not config.MOCK:
        from .meta_api import MetaASRSession
        return MetaASRSession(on_partial)
    return MockASRSession(on_partial)


def scene_model(live: bool):
    global _live_scene
    if live and not config.MOCK:
        if _live_scene is None:
            from .meta_api import MetaSceneModel
            _live_scene = MetaSceneModel()
        return _live_scene
    return MockSceneModel()


def image_model(live: bool):
    global _live_image
    if live and not config.MOCK:
        if _live_image is None:
            from .meta_api import MetaImageModel
            _live_image = MetaImageModel()
        return _live_image
    return MockImageModel()
