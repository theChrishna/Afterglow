"""Scene schema (validated with Pydantic), the backdrop bank, and the default scene."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ShaderStyle = Literal["grid", "rain", "nebula", "smoke", "aurora", "embers"]


class Lighting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intensity: float = Field(ge=0.0, le=1.0)
    warmth: float = Field(ge=-1.0, le=1.0)
    pulse_bpm: float = Field(ge=0.0, le=180.0)


class Shader(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: ShaderStyle
    speed: float = Field(ge=0.0, le=2.0)
    grain: float = Field(ge=0.0, le=1.0)


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mood: str = Field(min_length=1, max_length=40)
    palette: list[str] = Field(min_length=3, max_length=3)
    lighting: Lighting
    shader: Shader
    backdrop_prompt: str = Field(min_length=1, max_length=200)
    nearest_backdrop: str

    def model_post_init(self, _ctx) -> None:
        import re
        for c in self.palette:
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                raise ValueError(f"bad hex color {c!r}")
        if self.nearest_backdrop not in BANK_IDS:
            raise ValueError(f"unknown backdrop {self.nearest_backdrop!r}")


# Eight visually very different moods. Each entry doubles as the mock scene for that mood
# and as the prompt used by scripts/pregen_backdrops.py.
BANK: dict[str, dict] = {
    "neon_synth": {
        "label": "warm retro synth neon",
        "keywords": ["synth", "retro", "neon", "80s", "outrun", "arcade", "warm"],
        "prompt": "warm retro synthwave stage backdrop, glowing magenta and orange neon grid "
                  "horizon, giant soft sun, abstract, no text, no people",
        "scene": {"palette": ["#ff2e88", "#ff9f1c", "#2b0b3f"],
                  "lighting": {"intensity": 0.85, "warmth": 0.6, "pulse_bpm": 108},
                  "shader": {"style": "grid", "speed": 1.0, "grain": 0.25}},
    },
    "rain_city": {
        "label": "rainy city at 3am",
        "keywords": ["rain", "city", "night", "3am", "noir", "street", "wet", "lonely"],
        "prompt": "rainy city street at 3am seen through a wet window, blurred teal and sodium "
                  "streetlight bokeh, cinematic, moody, abstract, no text, no people",
        "scene": {"palette": ["#0b1a2e", "#2f7f9e", "#f2b544"],
                  "lighting": {"intensity": 0.4, "warmth": -0.4, "pulse_bpm": 0},
                  "shader": {"style": "rain", "speed": 0.7, "grain": 0.45}},
    },
    "deep_space": {
        "label": "deep space nebula",
        "keywords": ["space", "stars", "cosmic", "galaxy", "nebula", "float", "universe"],
        "prompt": "deep space nebula, violet and electric blue gas clouds, dense starfield, "
                  "vast and silent, abstract, no text, no planets with faces",
        "scene": {"palette": ["#05010f", "#6a2cff", "#33d1ff"],
                  "lighting": {"intensity": 0.55, "warmth": -0.2, "pulse_bpm": 0},
                  "shader": {"style": "nebula", "speed": 0.35, "grain": 0.15}},
    },
    "forest_mist": {
        "label": "misty forest dawn",
        "keywords": ["forest", "trees", "mist", "fog", "dawn", "green", "nature", "calm", "morning"],
        "prompt": "misty pine forest at dawn, soft green and pale gold light shafts through fog, "
                  "quiet and calm, painterly, no text, no people",
        "scene": {"palette": ["#0f2a1d", "#7fb069", "#e9e4b0"],
                  "lighting": {"intensity": 0.6, "warmth": 0.2, "pulse_bpm": 0},
                  "shader": {"style": "smoke", "speed": 0.3, "grain": 0.2}},
    },
    "desert_heat": {
        "label": "desert heat haze",
        "keywords": ["desert", "sand", "heat", "sun", "dune", "dry", "hot", "summer"],
        "prompt": "endless desert dunes under a blazing white sun, ochre and burnt orange, "
                  "shimmering heat haze, minimal, no text, no people",
        "scene": {"palette": ["#7a2e0e", "#e07a1f", "#ffe3a3"],
                  "lighting": {"intensity": 0.95, "warmth": 0.9, "pulse_bpm": 0},
                  "shader": {"style": "smoke", "speed": 0.6, "grain": 0.35}},
    },
    "ocean_calm": {
        "label": "underwater calm",
        "keywords": ["ocean", "sea", "water", "underwater", "waves", "blue", "dream", "slow"],
        "prompt": "calm underwater scene, pale aqua water with sunlight rays from the surface, "
                  "floating particles, serene, no text, no fish, no people",
        "scene": {"palette": ["#02303f", "#2ec4b6", "#cbf3f0"],
                  "lighting": {"intensity": 0.65, "warmth": -0.6, "pulse_bpm": 0},
                  "shader": {"style": "aurora", "speed": 0.25, "grain": 0.1}},
    },
    "ember_storm": {
        "label": "fire and embers",
        "keywords": ["fire", "ember", "rage", "angry", "intense", "energy", "strobe", "fast", "loud", "rock"],
        "prompt": "storm of glowing red embers and sparks rising through black smoke, intense, "
                  "dramatic, abstract, no text, no people",
        "scene": {"palette": ["#120000", "#d00000", "#ffba08"],
                  "lighting": {"intensity": 1.0, "warmth": 0.8, "pulse_bpm": 140},
                  "shader": {"style": "embers", "speed": 1.6, "grain": 0.4}},
    },
    "arctic_aurora": {
        "label": "arctic aurora",
        "keywords": ["aurora", "arctic", "ice", "snow", "cold", "northern", "winter", "frozen"],
        "prompt": "arctic night sky with vivid green and pink aurora curtains over snowy ice "
                  "plains, crisp and cold, no text, no people",
        "scene": {"palette": ["#020c1b", "#39ff9f", "#ff7ad9"],
                  "lighting": {"intensity": 0.7, "warmth": -0.8, "pulse_bpm": 0},
                  "shader": {"style": "aurora", "speed": 0.5, "grain": 0.15}},
    },
}
BANK_IDS = list(BANK)


def bank_scene(bank_id: str, mood: str | None = None) -> Scene:
    b = BANK[bank_id]
    return Scene(mood=(mood or b["label"])[:40], backdrop_prompt=b["prompt"][:200],
                 nearest_backdrop=bank_id, **b["scene"])


DEFAULT_SCENE = bank_scene("deep_space", "afterglow standby")


def match_bank(text: str, ignore: frozenset[str] = frozenset()) -> tuple[str, int]:
    """Cheap keyword match -> (bank id, score). Used by the mock scene model and offline fallback."""
    words = text.lower()
    best, score = "deep_space", 0
    for bid, b in BANK.items():
        s = sum(1 for k in b["keywords"] if k not in ignore and k in words)
        if s > score:
            best, score = bid, s
    return best, score


def nearest_bank_by_keywords(text: str) -> str:
    return match_bank(text)[0]


# Hand-written JSON schema for Muse Spark structured output (flat, no $defs).
SCENE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "mood": {"type": "string", "description": "2-5 word mood name"},
        "palette": {"type": "array", "items": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "minItems": 3, "maxItems": 3},
        "lighting": {
            "type": "object",
            "properties": {
                "intensity": {"type": "number", "minimum": 0, "maximum": 1},
                "warmth": {"type": "number", "minimum": -1, "maximum": 1},
                "pulse_bpm": {"type": "number", "minimum": 0, "maximum": 180},
            },
            "required": ["intensity", "warmth", "pulse_bpm"],
            "additionalProperties": False,
        },
        "shader": {
            "type": "object",
            "properties": {
                "style": {"type": "string", "enum": ["grid", "rain", "nebula", "smoke", "aurora", "embers"]},
                "speed": {"type": "number", "minimum": 0, "maximum": 2},
                "grain": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["style", "speed", "grain"],
            "additionalProperties": False,
        },
        "backdrop_prompt": {"type": "string"},
        "nearest_backdrop": {"type": "string", "enum": BANK_IDS},
    },
    "required": ["mood", "palette", "lighting", "shader", "backdrop_prompt", "nearest_backdrop"],
    "additionalProperties": False,
}
