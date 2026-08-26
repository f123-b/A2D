from __future__ import annotations

from .contract import (
    ExpressionBinding,
    ExpressionRule,
    HAIR_PARAMETER_BY_SEMANTIC,
    NormalizedRigInput,
    PhysicsRule,
    PlannedPart,
    QaFinding,
    REQUIRED_STANDARD_SEMANTICS,
    R8B_PARAMETER_IDS,
    RigPlanV1,
    Semantic,
)


PART_ID_BY_SEMANTIC: dict[Semantic, str] = {
    Semantic.BODY: "body",
    Semantic.CLOTH: "cloth",
    Semantic.FACE: "face",
    Semantic.BROW_L: "brow-l",
    Semantic.BROW_R: "brow-r",
    Semantic.EYE_WHITE_L: "eye-white-l",
    Semantic.EYE_WHITE_R: "eye-white-r",
    Semantic.IRIS_L: "iris-l",
    Semantic.IRIS_R: "iris-r",
    Semantic.MOUTH: "mouth",
    Semantic.HAIR_FRONT: "hair-front",
    Semantic.HAIR_SIDE_L: "hair-side-l",
    Semantic.HAIR_SIDE_R: "hair-side-r",
    Semantic.HAIR_BACK: "hair-back",
}

PARENT_BY_SEMANTIC: dict[Semantic, str | None] = {
    Semantic.BODY: None,
    Semantic.CLOTH: "body",
    Semantic.HAIR_BACK: "body",
    Semantic.FACE: "body",
    Semantic.BROW_L: "face",
    Semantic.BROW_R: "face",
    Semantic.EYE_WHITE_L: "face",
    Semantic.EYE_WHITE_R: "face",
    Semantic.IRIS_L: "eye-white-l",
    Semantic.IRIS_R: "eye-white-r",
    Semantic.MOUTH: "face",
    Semantic.HAIR_SIDE_L: "face",
    Semantic.HAIR_SIDE_R: "face",
    Semantic.HAIR_FRONT: "face",
}

DRAW_ORDER_BY_SEMANTIC: dict[Semantic, int] = {
    Semantic.HAIR_BACK: 0,
    Semantic.BODY: 1,
    Semantic.CLOTH: 2,
    Semantic.FACE: 3,
    Semantic.BROW_L: 4,
    Semantic.BROW_R: 4,
    Semantic.EYE_WHITE_L: 5,
    Semantic.EYE_WHITE_R: 5,
    Semantic.IRIS_L: 6,
    Semantic.IRIS_R: 6,
    Semantic.MOUTH: 7,
    Semantic.HAIR_SIDE_L: 8,
    Semantic.HAIR_SIDE_R: 8,
    Semantic.HAIR_FRONT: 9,
}


def _validate_input(value: NormalizedRigInput) -> None:
    if not value.character_id:
        raise ValueError("character_id is required")
    if value.canvas_width < 1 or value.canvas_height < 1:
        raise ValueError("canvas dimensions must be positive")

    ids: set[str] = set()
    semantic_counts: dict[Semantic, int] = {}
    for layer in value.layers:
        layer.validate()
        if layer.id in ids:
            raise ValueError(f"duplicate layer id: {layer.id}")
        ids.add(layer.id)
        semantic_counts[layer.semantic] = semantic_counts.get(layer.semantic, 0) + 1
        if layer.parent_id and layer.parent_id == layer.id:
            raise ValueError(f"layer {layer.id} cannot parent itself")

    for layer in value.layers:
        if layer.parent_id and layer.parent_id not in ids:
            raise ValueError(f"layer {layer.id} references missing parent {layer.parent_id}")

    for landmark in value.landmarks:
        landmark.validate()

    for semantic, count in semantic_counts.items():
        if semantic is not Semantic.ACCESSORY and count > 1:
            raise ValueError(f"semantic {semantic.value} appears {count} times")


def _findings(value: NormalizedRigInput) -> tuple[QaFinding, ...]:
    present = {layer.semantic for layer in value.layers}
    findings: list[QaFinding] = []
    for semantic in sorted(REQUIRED_STANDARD_SEMANTICS - present, key=lambda item: item.value):
        findings.append(QaFinding("error", "missing-required-semantic", f"missing required semantic layer: {semantic.value}"))

    for semantic in (Semantic.BROW_L, Semantic.BROW_R, Semantic.HAIR_FRONT, Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_BACK):
        if semantic not in present:
            findings.append(QaFinding("warning", "missing-optional-semantic", f"missing optional layer: {semantic.value}"))

    for layer in value.layers:
        if layer.confidence < 0.65:
            findings.append(QaFinding("warning", "low-layer-confidence", f"low confidence for {layer.semantic.value}: {layer.confidence:.2f}", layer.id))
    return tuple(findings)


def _expressions() -> tuple[ExpressionRule, ...]:
    return (
        ExpressionRule("happy", (
            ExpressionBinding("ParamMouthForm", "set", 0.75),
            ExpressionBinding("ParamBrowLY", "add", 0.25),
            ExpressionBinding("ParamBrowRY", "add", 0.25),
            ExpressionBinding("ParamEyeLOpen", "set", 0.88),
            ExpressionBinding("ParamEyeROpen", "set", 0.88),
        )),
        ExpressionRule("surprised", (
            ExpressionBinding("ParamMouthOpenY", "set", 0.95),
            ExpressionBinding("ParamBrowLY", "set", 0.75),
            ExpressionBinding("ParamBrowRY", "set", 0.75),
            ExpressionBinding("ParamEyeLOpen", "set", 1.0),
            ExpressionBinding("ParamEyeROpen", "set", 1.0),
        )),
        ExpressionRule("angry", (
            ExpressionBinding("ParamMouthForm", "set", -0.65),
            ExpressionBinding("ParamBrowLAngle", "set", -0.8),
            ExpressionBinding("ParamBrowRAngle", "set", -0.8),
        )),
    )


def compile_rig_plan(value: NormalizedRigInput) -> RigPlanV1:
    _validate_input(value)
    findings = _findings(value)
    if any(finding.severity == "error" for finding in findings):
        details = "; ".join(finding.message for finding in findings if finding.severity == "error")
        raise ValueError(details)

    parts: list[PlannedPart] = []
    for layer in value.layers:
        canonical_id = PART_ID_BY_SEMANTIC.get(layer.semantic)
        if canonical_id is None:
            canonical_id = f"accessory-{layer.id}"
            parent = "face"
            draw_order = 10 + layer.z_order
        else:
            parent = PARENT_BY_SEMANTIC[layer.semantic]
            draw_order = DRAW_ORDER_BY_SEMANTIC[layer.semantic]
        parts.append(PlannedPart(canonical_id, layer.id, layer.semantic, parent, draw_order))

    parts.sort(key=lambda part: (part.draw_order, part.id))

    physics: list[PhysicsRule] = []
    for semantic, output_parameter in HAIR_PARAMETER_BY_SEMANTIC.items():
        part_id = PART_ID_BY_SEMANTIC[semantic]
        if any(part.semantic == semantic for part in parts):
            nodes = 8 if semantic is Semantic.HAIR_BACK else 7 if semantic in (Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R) else 6
            physics.append(PhysicsRule(
                id=f"{part_id}-sway",
                source_part_id=part_id,
                input_parameter="ParamAngleX",
                output_parameter=output_parameter,
                node_count=nodes,
            ))

    return RigPlanV1(
        version=1,
        character_id=value.character_id,
        parts=tuple(parts),
        parameter_ids=R8B_PARAMETER_IDS,
        physics=tuple(physics),
        expressions=_expressions(),
        findings=findings,
    )
