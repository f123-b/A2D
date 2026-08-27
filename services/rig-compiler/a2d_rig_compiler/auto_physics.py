from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping

from .adaptive_mesh import AdaptiveMesh, Point2
from .compiler import compile_rig_plan
from .contract import (
    HAIR_PARAMETER_BY_SEMANTIC,
    NormalizedRigInput,
    QaFinding,
    RigPlanV1,
    Semantic,
)
from .semantic_rig import Pivot2, SemanticRigPlanV1, compile_semantic_rig


_HAIR_ORDER: tuple[Semantic, ...] = (
    Semantic.HAIR_FRONT,
    Semantic.HAIR_SIDE_L,
    Semantic.HAIR_SIDE_R,
    Semantic.HAIR_BACK,
)


@dataclass(frozen=True, slots=True)
class PhysicsInputBindingV1:
    parameter_id: str
    axis: str
    gain: float


@dataclass(frozen=True, slots=True)
class PhysicsOutputBindingV1:
    parameter_id: str
    axis: str
    source: str
    gain: float
    min: float
    max: float


@dataclass(frozen=True, slots=True)
class RuntimeSpringChainV1:
    id: str
    node_count: int
    segment_length: float
    root: Point2
    gravity: Point2
    damping: float
    stiffness: float
    input_bindings: tuple[PhysicsInputBindingV1, ...]
    output_bindings: tuple[PhysicsOutputBindingV1, ...]
    max_displacement: float

    def to_avatar_ir(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": "spring_chain",
            "nodeCount": self.node_count,
            "segmentLength": self.segment_length,
            "root": [self.root.x, self.root.y],
            "gravity": [self.gravity.x, self.gravity.y],
            "damping": self.damping,
            "stiffness": self.stiffness,
            "inputBindings": [
                {"parameterId": binding.parameter_id, "axis": binding.axis, "gain": binding.gain}
                for binding in self.input_bindings
            ],
            "outputBindings": [
                {
                    "parameterId": binding.parameter_id,
                    "axis": binding.axis,
                    "source": binding.source,
                    "gain": binding.gain,
                    "min": binding.min,
                    "max": binding.max,
                }
                for binding in self.output_bindings
            ],
            "maxDisplacement": self.max_displacement,
        }


@dataclass(frozen=True, slots=True)
class AutoPhysicsChainPlanV1:
    semantic: Semantic
    source_part_id: str
    root_source: str
    effective_length: float
    principal_direction: Point2
    verticality: float
    runtime: RuntimeSpringChainV1


@dataclass(frozen=True, slots=True)
class AutoPhysicsPlanV1:
    version: int
    character_id: str
    chains: tuple[AutoPhysicsChainPlanV1, ...]
    findings: tuple[QaFinding, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PhysicsCompileConfig:
    verticality_warning_threshold: float = 0.55
    short_segment_warning: float = 0.015
    min_max_displacement: float = 0.25
    max_displacement_scale: float = 2.2

    def validate(self) -> None:
        if not 0 <= self.verticality_warning_threshold <= 1:
            raise ValueError("verticality_warning_threshold must be 0..1")
        if not self.short_segment_warning > 0:
            raise ValueError("short_segment_warning must be > 0")
        if not self.min_max_displacement > 0:
            raise ValueError("min_max_displacement must be > 0")
        if not self.max_displacement_scale > 0:
            raise ValueError("max_displacement_scale must be > 0")


@dataclass(frozen=True, slots=True)
class _PhysicsPreset:
    target_segment: float
    min_nodes: int
    max_nodes: int
    gravity_y: float
    damping: float
    stiffness: float
    output_gain: float
    reference_length: float


_PRESET_BY_SEMANTIC: dict[Semantic, _PhysicsPreset] = {
    Semantic.HAIR_FRONT: _PhysicsPreset(0.052, 4, 8, 0.58, 0.10, 0.92, 2.0, 0.26),
    Semantic.HAIR_SIDE_L: _PhysicsPreset(0.075, 5, 9, 0.62, 0.12, 0.90, 1.8, 0.46),
    Semantic.HAIR_SIDE_R: _PhysicsPreset(0.075, 5, 9, 0.62, 0.12, 0.90, 1.8, 0.46),
    Semantic.HAIR_BACK: _PhysicsPreset(0.068, 6, 10, 0.68, 0.14, 0.88, 1.3, 0.48),
}

_ROOT_LANDMARK_BY_SEMANTIC: dict[Semantic, str] = {
    Semantic.HAIR_FRONT: "hair_front_root",
    Semantic.HAIR_SIDE_L: "hair_side_l_root",
    Semantic.HAIR_SIDE_R: "hair_side_r_root",
    Semantic.HAIR_BACK: "hair_back_root",
}


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _validate_mesh(mesh: AdaptiveMesh) -> None:
    if len(mesh.positions) < 2:
        raise ValueError("hair mesh must contain at least two vertices")
    for point in mesh.positions:
        if not math.isfinite(point.x) or not math.isfinite(point.y):
            raise ValueError("hair mesh positions must be finite")
        if point.x < 0 or point.x > 1 or point.y < 0 or point.y > 1:
            raise ValueError("hair mesh positions must remain normalized in [0,1]")


def _principal_direction(
    points: tuple[Point2, ...],
    root: Pivot2,
) -> tuple[Point2, float]:
    """Estimate the root-to-tip axis the Runtime v1 vertical chain is approximating."""
    tail_count = max(1, math.ceil(len(points) * 0.25))
    tail = sorted(points, key=lambda point: (-point.y, point.x))[:tail_count]
    tip_x = sum(point.x for point in tail) / len(tail)
    tip_y = sum(point.y for point in tail) / len(tail)
    dx = tip_x - root.x
    dy = tip_y - root.y
    distance = math.hypot(dx, dy)
    if distance < 1e-12:
        raise ValueError("hair mesh has zero root-to-tip extent")
    return Point2(dx / distance, dy / distance), abs(dy / distance)


def _root_source(
    semantic: Semantic,
    value: NormalizedRigInput,
) -> str:
    expected = _ROOT_LANDMARK_BY_SEMANTIC[semantic]
    if any(
        landmark.id == expected and landmark.confidence >= 0.5
        for landmark in value.landmarks
    ):
        return "landmark"
    return "bbox"


def _physics_pivot(
    source_part_id: str,
    semantic_rig: SemanticRigPlanV1,
) -> Pivot2:
    candidates = [
        deformer
        for deformer in semantic_rig.deformers
        if deformer.target_part_id == source_part_id and deformer.id.endswith("-physics")
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"expected one physics deformer for {source_part_id}, got {len(candidates)}"
        )
    return candidates[0].pivot


def compile_physics_chain(
    semantic: Semantic,
    source_part_id: str,
    output_parameter: str,
    mesh: AdaptiveMesh,
    root: Pivot2,
    *,
    root_source: str = "landmark",
    config: PhysicsCompileConfig | None = None,
) -> tuple[AutoPhysicsChainPlanV1, tuple[QaFinding, ...]]:
    if semantic not in _PRESET_BY_SEMANTIC:
        raise ValueError(f"unsupported physics semantic: {semantic.value}")
    expected_output = HAIR_PARAMETER_BY_SEMANTIC[semantic]
    if output_parameter != expected_output:
        raise ValueError(
            f"{semantic.value}: output parameter must be {expected_output}, got {output_parameter}"
        )
    if root_source not in {"landmark", "bbox"}:
        raise ValueError("root_source must be landmark or bbox")

    config = config or PhysicsCompileConfig()
    config.validate()
    _validate_mesh(mesh)
    if not math.isfinite(root.x) or not math.isfinite(root.y):
        raise ValueError("physics root must be finite")
    if root.x < 0 or root.x > 1 or root.y < 0 or root.y > 1:
        raise ValueError("physics root must remain normalized in [0,1]")

    direction, verticality = _principal_direction(mesh.positions, root)
    max_y = max(point.y for point in mesh.positions)
    effective_length = max_y - root.y
    if effective_length <= 1e-6:
        raise ValueError(
            f"{semantic.value}: hair mesh must extend below the physics root"
        )

    preset = _PRESET_BY_SEMANTIC[semantic]
    estimated_nodes = int(round(effective_length / preset.target_segment)) + 1
    node_count = max(preset.min_nodes, min(preset.max_nodes, estimated_nodes))
    segment_length = effective_length / (node_count - 1)

    length_factor = _clamp(effective_length / preset.reference_length, 0.5, 1.5)
    damping = _clamp(
        preset.damping + 0.03 * (length_factor - 1.0),
        0.06,
        0.25,
    )
    stiffness = _clamp(
        preset.stiffness - 0.05 * (length_factor - 1.0),
        0.75,
        0.97,
    )
    gravity_y = preset.gravity_y * (0.9 + 0.1 * length_factor)
    output_gain = _clamp(
        preset.output_gain
        * math.sqrt(preset.reference_length / max(effective_length, 1e-6)),
        0.8,
        3.0,
    )
    max_displacement = _clamp(
        effective_length * config.max_displacement_scale,
        config.min_max_displacement,
        1.25,
    )

    runtime = RuntimeSpringChainV1(
        id=f"{source_part_id}-sway",
        node_count=node_count,
        segment_length=segment_length,
        root=Point2(root.x, root.y),
        gravity=Point2(0.0, gravity_y),
        damping=damping,
        stiffness=stiffness,
        input_bindings=(
            PhysicsInputBindingV1("ParamAngleX", "x", 0.0025),
            PhysicsInputBindingV1("ParamBodyAngleX", "x", 0.0012),
        ),
        output_bindings=(
            PhysicsOutputBindingV1(
                output_parameter,
                "x",
                "tip",
                output_gain,
                -1.0,
                1.0,
            ),
        ),
        max_displacement=max_displacement,
    )

    findings: list[QaFinding] = []
    if verticality < config.verticality_warning_threshold:
        findings.append(
            QaFinding(
                "warning",
                "physics-nonvertical-geometry",
                (
                    f"{semantic.value} principal direction verticality "
                    f"{verticality:.3f} is below Runtime v1 threshold "
                    f"{config.verticality_warning_threshold:.3f}"
                ),
            )
        )
    if segment_length < config.short_segment_warning:
        findings.append(
            QaFinding(
                "warning",
                "physics-short-segment",
                (
                    f"{semantic.value} segment length {segment_length:.4f} is below "
                    f"{config.short_segment_warning:.4f}"
                ),
            )
        )

    return (
        AutoPhysicsChainPlanV1(
            semantic=semantic,
            source_part_id=source_part_id,
            root_source=root_source,
            effective_length=effective_length,
            principal_direction=direction,
            verticality=verticality,
            runtime=runtime,
        ),
        tuple(findings),
    )


def compile_auto_physics(
    value: NormalizedRigInput,
    meshes: Mapping[Semantic, AdaptiveMesh],
    rig_plan: RigPlanV1 | None = None,
    semantic_rig: SemanticRigPlanV1 | None = None,
    *,
    config: PhysicsCompileConfig | None = None,
) -> AutoPhysicsPlanV1:
    rig_plan = rig_plan or compile_rig_plan(value)
    if rig_plan.character_id != value.character_id:
        raise ValueError("rig plan character_id does not match input")
    semantic_rig = semantic_rig or compile_semantic_rig(value, rig_plan)
    if semantic_rig.character_id != value.character_id:
        raise ValueError("semantic rig character_id does not match input")

    layers = {layer.semantic: layer for layer in value.layers}
    parts = {part.semantic: part for part in rig_plan.parts}
    rules = {rule.source_part_id: rule for rule in rig_plan.physics}

    chains: list[AutoPhysicsChainPlanV1] = []
    findings: list[QaFinding] = []

    for semantic in _HAIR_ORDER:
        layer = layers.get(semantic)
        if layer is None:
            continue
        mesh = meshes.get(semantic)
        if mesh is None:
            raise ValueError(f"missing mesh for hair semantic: {semantic.value}")
        part = parts.get(semantic)
        if part is None:
            raise ValueError(f"rig plan missing part for hair semantic: {semantic.value}")
        rule = rules.get(part.id)
        if rule is None:
            raise ValueError(f"rig plan missing physics rule for part: {part.id}")

        expected_output = HAIR_PARAMETER_BY_SEMANTIC[semantic]
        if rule.output_parameter != expected_output:
            raise ValueError(
                f"{part.id}: physics output must be {expected_output}, got {rule.output_parameter}"
            )

        pivot = _physics_pivot(part.id, semantic_rig)
        chain, chain_findings = compile_physics_chain(
            semantic,
            part.id,
            rule.output_parameter,
            mesh,
            pivot,
            root_source=_root_source(semantic, value),
            config=config,
        )
        chains.append(chain)
        findings.extend(
            QaFinding(f.severity, f.code, f.message, layer.id)
            for f in chain_findings
        )

    findings.sort(key=lambda item: (item.severity, item.code, item.layer_id or ""))
    return AutoPhysicsPlanV1(1, value.character_id, tuple(chains), tuple(findings))
