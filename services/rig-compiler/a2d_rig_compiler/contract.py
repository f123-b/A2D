from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable


class Semantic(StrEnum):
    BODY = "body"
    CLOTH = "cloth"
    FACE = "face"
    BROW_L = "brow_l"
    BROW_R = "brow_r"
    EYE_WHITE_L = "eye_white_l"
    EYE_WHITE_R = "eye_white_r"
    IRIS_L = "iris_l"
    IRIS_R = "iris_r"
    MOUTH = "mouth"
    HAIR_FRONT = "hair_front"
    HAIR_SIDE_L = "hair_side_l"
    HAIR_SIDE_R = "hair_side_r"
    HAIR_BACK = "hair_back"
    ACCESSORY = "accessory"


@dataclass(frozen=True, slots=True)
class NormalizedRect:
    x: float
    y: float
    width: float
    height: float

    def validate(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(isinstance(v, (int, float)) for v in values):
            raise ValueError("bbox values must be numeric")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("bbox width/height must be > 0")
        if self.x < 0 or self.y < 0 or self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("bbox must remain inside normalized canvas [0,1]")


@dataclass(frozen=True, slots=True)
class SemanticLayer:
    id: str
    semantic: Semantic
    image_uri: str
    bbox: NormalizedRect
    z_order: int
    parent_id: str | None = None
    mask_uri: str | None = None
    confidence: float = 1.0

    def validate(self) -> None:
        if not self.id:
            raise ValueError("layer id is required")
        if not self.image_uri:
            raise ValueError(f"layer {self.id}: image_uri is required")
        self.bbox.validate()
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"layer {self.id}: confidence must be 0..1")


@dataclass(frozen=True, slots=True)
class Landmark:
    id: str
    x: float
    y: float
    confidence: float = 1.0

    def validate(self) -> None:
        if not self.id:
            raise ValueError("landmark id is required")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError(f"landmark {self.id}: coordinates must be normalized")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"landmark {self.id}: confidence must be 0..1")


@dataclass(frozen=True, slots=True)
class NormalizedRigInput:
    character_id: str
    canvas_width: int
    canvas_height: int
    layers: tuple[SemanticLayer, ...]
    landmarks: tuple[Landmark, ...] = ()
    source_revision: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedPart:
    id: str
    source_layer_id: str
    semantic: Semantic
    parent: str | None
    draw_order: int


@dataclass(frozen=True, slots=True)
class PhysicsRule:
    id: str
    source_part_id: str
    input_parameter: str
    output_parameter: str
    node_count: int


@dataclass(frozen=True, slots=True)
class ExpressionBinding:
    parameter_id: str
    mode: str
    value: float


@dataclass(frozen=True, slots=True)
class ExpressionRule:
    id: str
    bindings: tuple[ExpressionBinding, ...]


@dataclass(frozen=True, slots=True)
class QaFinding:
    severity: str
    code: str
    message: str
    layer_id: str | None = None


@dataclass(frozen=True, slots=True)
class RigPlanV1:
    version: int
    character_id: str
    parts: tuple[PlannedPart, ...]
    parameter_ids: tuple[str, ...]
    physics: tuple[PhysicsRule, ...]
    expressions: tuple[ExpressionRule, ...]
    findings: tuple[QaFinding, ...] = field(default_factory=tuple)


STANDARD_PARAMETER_IDS: tuple[str, ...] = (
    "ParamAngleX", "ParamAngleY", "ParamAngleZ",
    "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ", "ParamBreath",
    "ParamEyeLOpen", "ParamEyeROpen", "ParamEyeBallX", "ParamEyeBallY",
    "ParamMouthOpenY", "ParamMouthForm",
    "ParamBrowLY", "ParamBrowRY", "ParamBrowLAngle", "ParamBrowRAngle",
)

HAIR_PARAMETER_BY_SEMANTIC: dict[Semantic, str] = {
    Semantic.HAIR_FRONT: "ParamHairFrontX",
    Semantic.HAIR_SIDE_L: "ParamHairSideLX",
    Semantic.HAIR_SIDE_R: "ParamHairSideRX",
    Semantic.HAIR_BACK: "ParamHairBackX",
}

R8B_PARAMETER_IDS: tuple[str, ...] = STANDARD_PARAMETER_IDS + tuple(HAIR_PARAMETER_BY_SEMANTIC.values())

REQUIRED_STANDARD_SEMANTICS: frozenset[Semantic] = frozenset({
    Semantic.BODY,
    Semantic.FACE,
    Semantic.EYE_WHITE_L,
    Semantic.EYE_WHITE_R,
    Semantic.IRIS_L,
    Semantic.IRIS_R,
    Semantic.MOUTH,
})


def semantics(layers: Iterable[SemanticLayer]) -> frozenset[Semantic]:
    return frozenset(layer.semantic for layer in layers)
