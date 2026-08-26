from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .compiler import compile_rig_plan
from .contract import (
    HAIR_PARAMETER_BY_SEMANTIC,
    Landmark,
    NormalizedRect,
    NormalizedRigInput,
    QaFinding,
    RigPlanV1,
    Semantic,
    SemanticLayer,
)


class DeformerKind(StrEnum):
    WARP = "warp"
    ROTATION = "rotation"
    TRANSLATION = "translation"
    MORPH = "morph"
    PSEUDO3D_HEAD = "pseudo3d_head"


@dataclass(frozen=True, slots=True, order=True)
class Pivot2:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class ParameterBindingRule:
    parameter_id: str
    channel: str
    input_range: tuple[float, float]
    output_range: tuple[float, float]
    output_unit: str


@dataclass(frozen=True, slots=True)
class DeformerRule:
    id: str
    kind: DeformerKind
    target_part_id: str
    parent_deformer_id: str | None
    pivot: Pivot2
    bindings: tuple[ParameterBindingRule, ...]


@dataclass(frozen=True, slots=True)
class MorphIntent:
    id: str
    target_part_id: str
    parameter_id: str
    key_values: tuple[float, ...]
    operation: str
    amplitude: float
    amplitude_unit: str


@dataclass(frozen=True, slots=True)
class SemanticRigPlanV1:
    version: int
    character_id: str
    deformers: tuple[DeformerRule, ...]
    morph_intents: tuple[MorphIntent, ...]
    findings: tuple[QaFinding, ...] = field(default_factory=tuple)


_LANDMARK_ALIASES: dict[Semantic, tuple[str, ...]] = {
    Semantic.BODY: ("neck", "neck_center"),
    Semantic.FACE: ("head_center", "face_center", "nose"),
    Semantic.EYE_WHITE_L: ("eye_l_center", "left_eye_center"),
    Semantic.EYE_WHITE_R: ("eye_r_center", "right_eye_center"),
    Semantic.IRIS_L: ("iris_l_center", "eye_l_center", "left_eye_center"),
    Semantic.IRIS_R: ("iris_r_center", "eye_r_center", "right_eye_center"),
    Semantic.MOUTH: ("mouth_center",),
    Semantic.BROW_L: ("brow_l_center", "left_brow_center"),
    Semantic.BROW_R: ("brow_r_center", "right_brow_center"),
    Semantic.HAIR_FRONT: ("hair_front_root",),
    Semantic.HAIR_SIDE_L: ("hair_side_l_root",),
    Semantic.HAIR_SIDE_R: ("hair_side_r_root",),
    Semantic.HAIR_BACK: ("hair_back_root",),
}

_CRITICAL_PIVOT_SEMANTICS = frozenset({
    Semantic.BODY,
    Semantic.FACE,
    Semantic.EYE_WHITE_L,
    Semantic.EYE_WHITE_R,
    Semantic.MOUTH,
})


def _bbox_pivot(semantic: Semantic, bbox: NormalizedRect) -> Pivot2:
    if semantic is Semantic.BODY:
        return Pivot2(bbox.x + bbox.width * 0.5, bbox.y + bbox.height * 0.15)
    if semantic in {
        Semantic.HAIR_FRONT,
        Semantic.HAIR_SIDE_L,
        Semantic.HAIR_SIDE_R,
        Semantic.HAIR_BACK,
    }:
        return Pivot2(bbox.x + bbox.width * 0.5, bbox.y + bbox.height * 0.08)
    return Pivot2(bbox.x + bbox.width * 0.5, bbox.y + bbox.height * 0.5)


def _landmark_lookup(landmarks: tuple[Landmark, ...]) -> dict[str, Landmark]:
    result: dict[str, Landmark] = {}
    for landmark in landmarks:
        landmark.validate()
        if landmark.id in result:
            raise ValueError(f"duplicate landmark id: {landmark.id}")
        result[landmark.id] = landmark
    return result


def _resolve_pivot(
    semantic: Semantic,
    layer: SemanticLayer,
    landmarks: dict[str, Landmark],
) -> tuple[Pivot2, bool]:
    for landmark_id in _LANDMARK_ALIASES.get(semantic, ()):
        landmark = landmarks.get(landmark_id)
        if landmark is not None and landmark.confidence >= 0.5:
            return Pivot2(landmark.x, landmark.y), True
    return _bbox_pivot(semantic, layer.bbox), False


def _binding(
    parameter_id: str,
    channel: str,
    input_range: tuple[float, float],
    output_range: tuple[float, float],
    output_unit: str,
) -> ParameterBindingRule:
    return ParameterBindingRule(parameter_id, channel, input_range, output_range, output_unit)


def _part_id_by_semantic(plan: RigPlanV1) -> dict[Semantic, str]:
    result: dict[Semantic, str] = {}
    for part in plan.parts:
        if part.semantic is not Semantic.ACCESSORY:
            result[part.semantic] = part.id
    return result


def _layer_by_semantic(value: NormalizedRigInput) -> dict[Semantic, SemanticLayer]:
    result: dict[Semantic, SemanticLayer] = {}
    for layer in value.layers:
        if layer.semantic is not Semantic.ACCESSORY:
            result[layer.semantic] = layer
    return result


def _morph_intents(part_ids: dict[Semantic, str], layers: dict[Semantic, SemanticLayer]) -> list[MorphIntent]:
    out: list[MorphIntent] = []
    if Semantic.BODY in part_ids:
        out.append(MorphIntent(
            "body-breath", part_ids[Semantic.BODY], "ParamBreath",
            (0.0, 1.0), "body_breath_scale_y", 0.015, "bbox_height",
        ))
    for semantic, parameter in (
        (Semantic.EYE_WHITE_L, "ParamEyeLOpen"),
        (Semantic.EYE_WHITE_R, "ParamEyeROpen"),
    ):
        if semantic in part_ids:
            out.append(MorphIntent(
                f"{part_ids[semantic]}-blink", part_ids[semantic], parameter,
                (0.0, 1.0), "eye_close_y", 0.48, "bbox_height",
            ))
    if Semantic.MOUTH in part_ids:
        mouth = part_ids[Semantic.MOUTH]
        out.extend((
            MorphIntent("mouth-open", mouth, "ParamMouthOpenY", (0.0, 1.0), "mouth_open_y", 0.38, "bbox_height"),
            MorphIntent("mouth-form", mouth, "ParamMouthForm", (-1.0, 0.0, 1.0), "mouth_form_x", 0.22, "bbox_width"),
        ))
    for semantic, y_parameter, angle_parameter in (
        (Semantic.BROW_L, "ParamBrowLY", "ParamBrowLAngle"),
        (Semantic.BROW_R, "ParamBrowRY", "ParamBrowRAngle"),
    ):
        if semantic in part_ids:
            part_id = part_ids[semantic]
            out.extend((
                MorphIntent(f"{part_id}-y", part_id, y_parameter, (-1.0, 0.0, 1.0), "brow_translate_y", 0.20, "bbox_height"),
                MorphIntent(f"{part_id}-angle", part_id, angle_parameter, (-1.0, 0.0, 1.0), "brow_rotate", 12.0, "degrees"),
            ))
    return out


def compile_semantic_rig(
    value: NormalizedRigInput,
    rig_plan: RigPlanV1 | None = None,
) -> SemanticRigPlanV1:
    """Compile semantic rig rules without touching mesh topology."""
    plan = rig_plan or compile_rig_plan(value)
    if plan.character_id != value.character_id:
        raise ValueError("rig plan character_id does not match input")

    layers = _layer_by_semantic(value)
    part_ids = _part_id_by_semantic(plan)
    landmarks = _landmark_lookup(value.landmarks)
    findings: list[QaFinding] = []
    pivots: dict[Semantic, Pivot2] = {}

    for semantic, layer in sorted(layers.items(), key=lambda item: item[0].value):
        pivot, used_landmark = _resolve_pivot(semantic, layer, landmarks)
        pivots[semantic] = pivot
        if semantic in _CRITICAL_PIVOT_SEMANTICS and not used_landmark:
            findings.append(QaFinding("warning", "pivot-bbox-fallback", f"{semantic.value} pivot used bbox fallback", layer.id))

    deformers: list[DeformerRule] = []
    body_part = part_ids.get(Semantic.BODY)
    if body_part is not None:
        deformers.append(DeformerRule(
            "body-motion", DeformerKind.WARP, body_part, None, pivots[Semantic.BODY],
            (
                _binding("ParamBodyAngleX", "translate_x", (-10.0, 10.0), (-0.018, 0.018), "canvas_width"),
                _binding("ParamBodyAngleY", "translate_y", (-10.0, 10.0), (-0.012, 0.012), "canvas_height"),
                _binding("ParamBodyAngleZ", "roll", (-10.0, 10.0), (-8.0, 8.0), "degrees"),
            ),
        ))

    face_part = part_ids.get(Semantic.FACE)
    if face_part is not None:
        deformers.append(DeformerRule(
            "head-pseudo3d", DeformerKind.PSEUDO3D_HEAD, face_part,
            "body-motion" if body_part is not None else None, pivots[Semantic.FACE],
            (
                _binding("ParamAngleX", "yaw", (-30.0, 30.0), (-30.0, 30.0), "degrees"),
                _binding("ParamAngleY", "pitch", (-30.0, 30.0), (-30.0, 30.0), "degrees"),
                _binding("ParamAngleZ", "roll", (-30.0, 30.0), (-30.0, 30.0), "degrees"),
            ),
        ))

    for semantic, open_parameter, node_id in (
        (Semantic.EYE_WHITE_L, "ParamEyeLOpen", "eye-l-blink"),
        (Semantic.EYE_WHITE_R, "ParamEyeROpen", "eye-r-blink"),
    ):
        part_id = part_ids.get(semantic)
        if part_id is not None:
            deformers.append(DeformerRule(
                node_id, DeformerKind.MORPH, part_id,
                "head-pseudo3d" if face_part is not None else None, pivots[semantic],
                (_binding(open_parameter, "open", (0.0, 1.0), (0.0, 1.0), "normalized"),),
            ))

    for semantic, node_id, parent_node in (
        (Semantic.IRIS_L, "iris-l-gaze", "eye-l-blink"),
        (Semantic.IRIS_R, "iris-r-gaze", "eye-r-blink"),
    ):
        part_id = part_ids.get(semantic)
        if part_id is not None:
            deformers.append(DeformerRule(
                node_id, DeformerKind.TRANSLATION, part_id, parent_node, pivots[semantic],
                (
                    _binding("ParamEyeBallX", "translate_x", (-1.0, 1.0), (-0.12, 0.12), "bbox_width"),
                    _binding("ParamEyeBallY", "translate_y", (-1.0, 1.0), (-0.10, 0.10), "bbox_height"),
                ),
            ))

    mouth_part = part_ids.get(Semantic.MOUTH)
    if mouth_part is not None:
        deformers.append(DeformerRule(
            "mouth-morph", DeformerKind.MORPH, mouth_part,
            "head-pseudo3d" if face_part is not None else None, pivots[Semantic.MOUTH],
            (
                _binding("ParamMouthOpenY", "open", (0.0, 1.0), (0.0, 1.0), "normalized"),
                _binding("ParamMouthForm", "form", (-1.0, 1.0), (-1.0, 1.0), "normalized"),
            ),
        ))

    for semantic, node_id, y_parameter, angle_parameter in (
        (Semantic.BROW_L, "brow-l-motion", "ParamBrowLY", "ParamBrowLAngle"),
        (Semantic.BROW_R, "brow-r-motion", "ParamBrowRY", "ParamBrowRAngle"),
    ):
        part_id = part_ids.get(semantic)
        if part_id is not None:
            deformers.append(DeformerRule(
                node_id, DeformerKind.MORPH, part_id,
                "head-pseudo3d" if face_part is not None else None, pivots[semantic],
                (
                    _binding(y_parameter, "translate_y", (-1.0, 1.0), (-0.20, 0.20), "bbox_height"),
                    _binding(angle_parameter, "roll", (-1.0, 1.0), (-12.0, 12.0), "degrees"),
                ),
            ))

    for semantic, output_parameter in HAIR_PARAMETER_BY_SEMANTIC.items():
        part_id = part_ids.get(semantic)
        if part_id is None:
            continue
        parent = "body-motion" if semantic is Semantic.HAIR_BACK else "head-pseudo3d"
        if semantic is Semantic.HAIR_BACK and body_part is None:
            parent = None
        if semantic is not Semantic.HAIR_BACK and face_part is None:
            parent = None
        deformers.append(DeformerRule(
            f"{part_id}-physics", DeformerKind.ROTATION, part_id, parent, pivots[semantic],
            (_binding(output_parameter, "sway", (-1.0, 1.0), (-16.0, 16.0), "degrees"),),
        ))

    deformer_order = {
        "body-motion": 0, "head-pseudo3d": 10,
        "eye-l-blink": 20, "eye-r-blink": 21,
        "iris-l-gaze": 30, "iris-r-gaze": 31,
        "mouth-morph": 40, "brow-l-motion": 50, "brow-r-motion": 51,
        "hair-back-physics": 60, "hair-side-l-physics": 61,
        "hair-side-r-physics": 62, "hair-front-physics": 63,
    }
    deformers.sort(key=lambda item: (deformer_order.get(item.id, 1000), item.id))

    intents = _morph_intents(part_ids, layers)
    intents.sort(key=lambda item: item.id)
    findings.sort(key=lambda item: (item.severity, item.code, item.layer_id or ""))

    ids = {item.id for item in deformers}
    for item in deformers:
        if item.parent_deformer_id is not None and item.parent_deformer_id not in ids:
            raise ValueError(f"deformer {item.id} references missing parent {item.parent_deformer_id}")

    return SemanticRigPlanV1(1, value.character_id, tuple(deformers), tuple(intents), tuple(findings))
