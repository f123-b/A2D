from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct
from typing import Iterable

from .adaptive_mesh import AdaptiveMesh
from .compiler import compile_rig_plan
from .contract import NormalizedRect, NormalizedRigInput, QaFinding, RigPlanV1, Semantic
from .semantic_rig import MorphIntent, Pivot2, SemanticRigPlanV1, compile_semantic_rig


MORPH_INFLUENCE_STRIDE_BYTES = 16
MORPH_RANGE_STRIDE_BYTES = 8


@dataclass(frozen=True, slots=True)
class MorphCompileConfig:
    min_weight: float = 1e-4
    max_influences_per_vertex: int = 8

    def validate(self) -> None:
        if not math.isfinite(self.min_weight) or not 0 <= self.min_weight < 1:
            raise ValueError("min_weight must be finite in [0,1)")
        if not 1 <= self.max_influences_per_vertex <= 8:
            raise ValueError("max_influences_per_vertex must be 1..8")


@dataclass(frozen=True, slots=True)
class MorphInfluenceRecord:
    vertex_index: int
    parameter_index: int
    intent_id: str
    delta_x: float
    delta_y: float
    weight: float


@dataclass(frozen=True, slots=True)
class MorphVertexRange:
    start: int
    count: int


@dataclass(frozen=True, slots=True)
class CompiledMorphPlanV1:
    version: int
    target_part_id: str
    semantic: Semantic
    records: tuple[MorphInfluenceRecord, ...]
    ranges: tuple[MorphVertexRange, ...]
    findings: tuple[QaFinding, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PackedMorphBuffers:
    influences: bytes
    ranges: bytes


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _smooth01(value: float) -> float:
    value = _clamp01(value)
    return value * value * (3.0 - 2.0 * value)


def _local_xy(point, bbox: NormalizedRect) -> tuple[float, float]:
    return (
        _clamp01((point.x - bbox.x) / bbox.width),
        _clamp01((point.y - bbox.y) / bbox.height),
    )


def _default_pivot(semantic: Semantic, bbox: NormalizedRect) -> Pivot2:
    if semantic is Semantic.BODY:
        return Pivot2(bbox.x + bbox.width * 0.5, bbox.y + bbox.height * 0.15)
    return Pivot2(bbox.x + bbox.width * 0.5, bbox.y + bbox.height * 0.5)


def _validate_intent(intent: MorphIntent) -> None:
    if not intent.id:
        raise ValueError("morph intent id is required")
    if not intent.parameter_id:
        raise ValueError(f"morph intent {intent.id}: parameter_id is required")
    if not intent.key_values or any(not math.isfinite(value) for value in intent.key_values):
        raise ValueError(f"morph intent {intent.id}: key_values must be finite and non-empty")
    if tuple(sorted(set(intent.key_values))) != intent.key_values:
        raise ValueError(f"morph intent {intent.id}: key_values must be unique and sorted")
    if not math.isfinite(intent.amplitude) or intent.amplitude < 0:
        raise ValueError(f"morph intent {intent.id}: amplitude must be finite and >= 0")


def _compile_delta(
    intent: MorphIntent,
    point,
    bbox: NormalizedRect,
    pivot: Pivot2,
) -> tuple[float, float, float]:
    u, _ = _local_xy(point, bbox)

    if intent.operation == "eye_close_y":
        corner_weight = _smooth01(math.sin(math.pi * u))
        dy = (point.y - pivot.y) * 0.96
        max_delta = intent.amplitude * bbox.height
        dy = max(-max_delta, min(max_delta, dy))
        return 0.0, dy, corner_weight

    if intent.operation == "mouth_open_y":
        vertical = (point.y - pivot.y) / max(1e-12, bbox.height * 0.5)
        center_weight = _smooth01(1.0 - abs(u - 0.5) * 2.0)
        weight = 0.25 + 0.75 * center_weight
        dy = max(-1.0, min(1.0, vertical)) * intent.amplitude * bbox.height
        return 0.0, dy, weight

    if intent.operation == "mouth_form_x":
        signed = (point.x - pivot.x) / max(1e-12, bbox.width * 0.5)
        signed = max(-1.0, min(1.0, signed))
        corner_weight = _smooth01(abs(signed))
        dx = signed * intent.amplitude * bbox.width
        dy = -corner_weight * intent.amplitude * bbox.height * 0.30
        return dx, dy, max(0.15, corner_weight)

    if intent.operation == "brow_translate_y":
        return 0.0, -intent.amplitude * bbox.height, 1.0

    if intent.operation == "brow_rotate":
        radians = math.radians(intent.amplitude)
        c = math.cos(radians)
        s = math.sin(radians)
        x0 = point.x - pivot.x
        y0 = point.y - pivot.y
        rx = c * x0 - s * y0
        ry = s * x0 + c * y0
        return rx - x0, ry - y0, 1.0

    if intent.operation == "body_breath_scale_y":
        return 0.0, (point.y - pivot.y) * intent.amplitude, 1.0

    raise ValueError(f"unsupported morph operation: {intent.operation}")


def compile_morph_plan(
    target_part_id: str,
    semantic: Semantic,
    bbox: NormalizedRect,
    mesh: AdaptiveMesh,
    intents: Iterable[MorphIntent],
    parameter_ids: tuple[str, ...],
    pivot: Pivot2 | None = None,
    config: MorphCompileConfig | None = None,
) -> CompiledMorphPlanV1:
    config = config or MorphCompileConfig()
    config.validate()
    bbox.validate()
    if len(mesh.positions) != len(mesh.uvs):
        raise ValueError("mesh position/uv length mismatch")

    parameter_index: dict[str, int] = {}
    for index, parameter_id in enumerate(parameter_ids):
        if parameter_id in parameter_index:
            raise ValueError(f"duplicate parameter id: {parameter_id}")
        parameter_index[parameter_id] = index

    selected = sorted(
        (intent for intent in intents if intent.target_part_id == target_part_id),
        key=lambda item: item.id,
    )
    for intent in selected:
        _validate_intent(intent)
    for point in mesh.positions:
        if not math.isfinite(point.x) or not math.isfinite(point.y):
            raise ValueError("mesh positions must be finite")
    actual_pivot = pivot or _default_pivot(semantic, bbox)

    records: list[MorphInfluenceRecord] = []
    ranges: list[MorphVertexRange] = []
    for vertex_index, point in enumerate(mesh.positions):
        start = len(records)
        local_records: list[MorphInfluenceRecord] = []
        for intent in selected:
            index = parameter_index.get(intent.parameter_id)
            if index is None:
                raise ValueError(
                    f"morph intent {intent.id} references unknown parameter {intent.parameter_id}"
                )
            delta_x, delta_y, weight = _compile_delta(intent, point, bbox, actual_pivot)
            if not all(math.isfinite(value) for value in (delta_x, delta_y, weight)):
                raise ValueError(f"morph intent {intent.id} produced non-finite influence")
            weight = _clamp01(weight)
            if weight < config.min_weight:
                continue
            if abs(delta_x) < 1e-12 and abs(delta_y) < 1e-12:
                continue
            local_records.append(MorphInfluenceRecord(
                vertex_index=vertex_index,
                parameter_index=index,
                intent_id=intent.id,
                delta_x=delta_x,
                delta_y=delta_y,
                weight=weight,
            ))

        local_records.sort(key=lambda item: (item.parameter_index, item.intent_id))
        if len(local_records) > config.max_influences_per_vertex:
            raise ValueError(
                f"vertex {vertex_index} has {len(local_records)} morph influences; "
                f"limit is {config.max_influences_per_vertex}"
            )
        records.extend(local_records)
        ranges.append(MorphVertexRange(start, len(local_records)))

    return CompiledMorphPlanV1(
        version=1,
        target_part_id=target_part_id,
        semantic=semantic,
        records=tuple(records),
        ranges=tuple(ranges),
    )


def _part_and_bbox(
    value: NormalizedRigInput,
    rig_plan: RigPlanV1,
    semantic: Semantic,
) -> tuple[str, NormalizedRect]:
    layer = next((item for item in value.layers if item.semantic is semantic), None)
    part = next((item for item in rig_plan.parts if item.semantic is semantic), None)
    if layer is None or part is None:
        raise ValueError(f"semantic {semantic.value} is not present in rig input")
    return part.id, layer.bbox


def _pivot_for_part(
    semantic_rig: SemanticRigPlanV1,
    target_part_id: str,
    semantic: Semantic,
    bbox: NormalizedRect,
) -> Pivot2:
    candidates = sorted(
        (item for item in semantic_rig.deformers if item.target_part_id == target_part_id),
        key=lambda item: item.id,
    )
    if candidates:
        return candidates[0].pivot
    return _default_pivot(semantic, bbox)


def compile_semantic_morphs(
    value: NormalizedRigInput,
    semantic: Semantic,
    mesh: AdaptiveMesh,
    rig_plan: RigPlanV1 | None = None,
    semantic_rig: SemanticRigPlanV1 | None = None,
    config: MorphCompileConfig | None = None,
) -> CompiledMorphPlanV1:
    plan = rig_plan or compile_rig_plan(value)
    if plan.character_id != value.character_id:
        raise ValueError("rig plan character_id does not match input")
    rig = semantic_rig or compile_semantic_rig(value, plan)
    if rig.character_id != value.character_id:
        raise ValueError("semantic rig character_id does not match input")

    target_part_id, bbox = _part_and_bbox(value, plan, semantic)
    pivot = _pivot_for_part(rig, target_part_id, semantic, bbox)
    return compile_morph_plan(
        target_part_id=target_part_id,
        semantic=semantic,
        bbox=bbox,
        mesh=mesh,
        intents=rig.morph_intents,
        parameter_ids=plan.parameter_ids,
        pivot=pivot,
        config=config,
    )


def _validate_plan_layout(plan: CompiledMorphPlanV1) -> None:
    expected_start = 0
    for vertex_index, item in enumerate(plan.ranges):
        if item.start != expected_start:
            raise ValueError(f"morph range {vertex_index} is not contiguous")
        if item.count < 0 or item.count > 8:
            raise ValueError(f"morph range {vertex_index} count must be 0..8")
        end = item.start + item.count
        if end > len(plan.records):
            raise ValueError(f"morph range {vertex_index} exceeds record count")
        for record in plan.records[item.start:end]:
            if record.vertex_index != vertex_index:
                raise ValueError(f"morph record vertex mismatch at vertex {vertex_index}")
            if not 0 <= record.parameter_index <= 0xFFFFFFFF:
                raise ValueError("parameter index must fit u32")
            if not all(math.isfinite(value) for value in (record.delta_x, record.delta_y, record.weight)):
                raise ValueError("morph influence values must be finite")
            if not 0 <= record.weight <= 1:
                raise ValueError("morph influence weight must be 0..1")
        expected_start = end
    if expected_start != len(plan.records):
        raise ValueError("morph records are not fully covered by ranges")


def pack_morph_influences(plan: CompiledMorphPlanV1) -> bytes:
    _validate_plan_layout(plan)
    out = bytearray(len(plan.records) * MORPH_INFLUENCE_STRIDE_BYTES)
    for index, record in enumerate(plan.records):
        struct.pack_into(
            "<Ifff",
            out,
            index * MORPH_INFLUENCE_STRIDE_BYTES,
            record.parameter_index,
            record.delta_x,
            record.delta_y,
            record.weight,
        )
    return bytes(out)


def pack_morph_ranges(plan: CompiledMorphPlanV1) -> bytes:
    _validate_plan_layout(plan)
    out = bytearray(len(plan.ranges) * MORPH_RANGE_STRIDE_BYTES)
    for index, item in enumerate(plan.ranges):
        if not 0 <= item.start <= 0xFFFFFFFF or not 0 <= item.count <= 0xFFFFFFFF:
            raise ValueError("morph range values must fit u32")
        struct.pack_into(
            "<II",
            out,
            index * MORPH_RANGE_STRIDE_BYTES,
            item.start,
            item.count,
        )
    return bytes(out)


def pack_morph_buffers(plan: CompiledMorphPlanV1) -> PackedMorphBuffers:
    return PackedMorphBuffers(
        influences=pack_morph_influences(plan),
        ranges=pack_morph_ranges(plan),
    )
