import pytest
from pydantic import ValidationError

from app.scene import BANK, BANK_IDS, DEFAULT_SCENE, SCENE_JSON_SCHEMA, Scene, bank_scene, match_bank


def test_every_bank_entry_is_a_valid_scene():
    for bid in BANK_IDS:
        assert bank_scene(bid).nearest_backdrop == bid


def test_schema_matches_model_fields():
    assert set(SCENE_JSON_SCHEMA["required"]) == set(Scene.model_fields)
    assert SCENE_JSON_SCHEMA["properties"]["nearest_backdrop"]["enum"] == BANK_IDS


@pytest.mark.parametrize("patch", [
    {"palette": ["#000000", "#ffffff"]},
    {"palette": ["#000000", "#ffffff", "red"]},
    {"nearest_backdrop": "nope"},
    {"lighting": {"intensity": 2, "warmth": 0, "pulse_bpm": 0}},
    {"shader": {"style": "lava", "speed": 1, "grain": 0}},
    {"extra": 1},
])
def test_invalid_scenes_rejected(patch):
    data = DEFAULT_SCENE.model_dump() | patch
    with pytest.raises(ValidationError):
        Scene.model_validate(data)


def test_keyword_match():
    assert match_bank("make it feel like a rainy city at 3am")[0] == "rain_city"
    assert match_bank("hello there")[1] == 0
    assert len({b["scene"]["shader"]["style"] for b in BANK.values()}) >= 5  # visually varied
