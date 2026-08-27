from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import math
import struct
from typing import Mapping
import zipfile

from .adaptive_mesh import AdaptiveMesh, AlphaMask, MeshGenerationError, Point2, generate_layer_mesh
from .auto_physics import AutoPhysicsPlanV1, compile_auto_physics
from .compiler import compile_rig_plan
from .contract import NormalizedRigInput, RigPlanV1, Semantic
from .facial_morph import CompiledMorphPlanV1, compile_semantic_morphs
from .proxy_z import ProxyZHeadPlanV1, compile_proxy_z_head
from .qa import (
    CompileQaConfig, CompileQaFindingV1, CompileQaReportV1, QaStage,
    StageQaSummaryV1, compile_qa_report,
)
from .semantic_rig import DeformerKind, SemanticRigPlanV1, compile_semantic_rig


@dataclass(frozen=True, slots=True)
class RgbaImage:
    width: int
    height: int
    pixels: bytes

    def validate(self) -> None:
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise ValueError("RGBA image width/height must be integers")
        if self.width < 1 or self.height < 1:
            raise ValueError("RGBA image width/height must be positive")
        if len(self.pixels) != self.width * self.height * 4:
            raise ValueError(
                f"RGBA image byte length {len(self.pixels)} does not equal "
                f"{self.width}*{self.height}*4"
            )


@dataclass(frozen=True, slots=True)
class AtlasConfig:
    padding: int = 2
    max_size: int = 4096

    def validate(self) -> None:
        if not isinstance(self.padding, int) or not 1 <= self.padding <= 16:
            raise ValueError("atlas padding must be an integer in 1..16")
        if not isinstance(self.max_size, int) or not 16 <= self.max_size <= 16384:
            raise ValueError("atlas max_size must be an integer in 16..16384")


@dataclass(frozen=True, slots=True)
class AtlasPlacementV1:
    layer_id: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class CompiledAtlasV1:
    width: int
    height: int
    pixels: bytes
    placements: tuple[AtlasPlacementV1, ...]


@dataclass(frozen=True, slots=True)
class CompiledAvatarArtifactV1:
    manifest: dict[str, object]
    model: dict[str, object]
    geometry: bytes
    atlas: CompiledAtlasV1
    qa_json: bytes
    a2d: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class OneClickCompileResultV1:
    version: int
    character_id: str
    qa: CompileQaReportV1
    artifact: CompiledAvatarArtifactV1 | None


@dataclass(frozen=True, slots=True)
class _Segment:
    byte_offset: int
    byte_length: int


class _BinaryBuilder:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def append(self, payload: bytes) -> _Segment:
        while len(self._buffer) % 4:
            self._buffer.append(0)
        segment = _Segment(len(self._buffer), len(payload))
        self._buffer.extend(payload)
        return segment

    def finish(self) -> bytes:
        while len(self._buffer) % 4:
            self._buffer.append(0)
        return bytes(self._buffer)


_PART_SEMANTIC: dict[Semantic, str] = {
    Semantic.BODY: "body", Semantic.CLOTH: "cloth", Semantic.FACE: "face",
    Semantic.BROW_L: "other", Semantic.BROW_R: "other",
    Semantic.EYE_WHITE_L: "eye_l", Semantic.EYE_WHITE_R: "eye_r",
    Semantic.IRIS_L: "iris_l", Semantic.IRIS_R: "iris_r", Semantic.MOUTH: "mouth",
    Semantic.HAIR_FRONT: "hair_front", Semantic.HAIR_SIDE_L: "hair_side",
    Semantic.HAIR_SIDE_R: "hair_side", Semantic.HAIR_BACK: "hair_back",
    Semantic.ACCESSORY: "accessory",
}

_PARAMETER_SPEC: dict[str, tuple[float, float, float]] = {
    "ParamAngleX": (-30.0, 30.0, 0.0), "ParamAngleY": (-30.0, 30.0, 0.0),
    "ParamAngleZ": (-30.0, 30.0, 0.0), "ParamBodyAngleX": (-20.0, 20.0, 0.0),
    "ParamBodyAngleY": (-20.0, 20.0, 0.0), "ParamBodyAngleZ": (-20.0, 20.0, 0.0),
    "ParamBreath": (0.0, 1.0, 0.0), "ParamEyeLOpen": (0.0, 1.0, 1.0),
    "ParamEyeROpen": (0.0, 1.0, 1.0), "ParamEyeBallX": (-1.0, 1.0, 0.0),
    "ParamEyeBallY": (-1.0, 1.0, 0.0), "ParamMouthOpenY": (0.0, 1.0, 0.0),
    "ParamMouthForm": (-1.0, 1.0, 0.0), "ParamBrowLY": (-1.0, 1.0, 0.0),
    "ParamBrowRY": (-1.0, 1.0, 0.0), "ParamBrowLAngle": (-1.0, 1.0, 0.0),
    "ParamBrowRAngle": (-1.0, 1.0, 0.0), "ParamHairFrontX": (-1.0, 1.0, 0.0),
    "ParamHairSideLX": (-1.0, 1.0, 0.0), "ParamHairSideRX": (-1.0, 1.0, 0.0),
    "ParamHairBackX": (-1.0, 1.0, 0.0),
}

_HEAD_SEMANTICS = frozenset({
    Semantic.FACE, Semantic.BROW_L, Semantic.BROW_R,
    Semantic.EYE_WHITE_L, Semantic.EYE_WHITE_R, Semantic.IRIS_L, Semantic.IRIS_R,
    Semantic.MOUTH, Semantic.HAIR_FRONT, Semantic.HAIR_SIDE_L,
    Semantic.HAIR_SIDE_R, Semantic.HAIR_BACK,
})


def _next_pow2(value: int) -> int:
    return 1 << max(0, value - 1).bit_length()


def _pack_shelves(
    ordered: tuple[tuple[str, RgbaImage], ...], width: int, padding: int, max_size: int,
) -> tuple[list[AtlasPlacementV1], int] | None:
    x = y = row_height = 0
    placements: list[AtlasPlacementV1] = []
    for layer_id, image in ordered:
        padded_width = image.width + padding * 2
        padded_height = image.height + padding * 2
        if padded_width > width:
            return None
        if x and x + padded_width > width:
            y += row_height
            x = row_height = 0
        if y + padded_height > max_size:
            return None
        placements.append(AtlasPlacementV1(layer_id, x + padding, y + padding, image.width, image.height))
        x += padded_width
        row_height = max(row_height, padded_height)
    return placements, y + row_height


def _copy_with_gutter(
    atlas: bytearray, atlas_width: int, image: RgbaImage,
    placement: AtlasPlacementV1, padding: int,
) -> None:
    for dy in range(-padding, image.height + padding):
        source_y = min(image.height - 1, max(0, dy))
        atlas_y = placement.y + dy
        for dx in range(-padding, image.width + padding):
            source_x = min(image.width - 1, max(0, dx))
            atlas_x = placement.x + dx
            source_offset = (source_y * image.width + source_x) * 4
            atlas_offset = (atlas_y * atlas_width + atlas_x) * 4
            atlas[atlas_offset:atlas_offset + 4] = image.pixels[source_offset:source_offset + 4]


def build_texture_atlas(
    value: NormalizedRigInput, images: Mapping[str, RgbaImage], *,
    config: AtlasConfig | None = None,
) -> CompiledAtlasV1:
    config = config or AtlasConfig()
    config.validate()
    required_ids = {layer.id for layer in value.layers}
    missing = sorted(required_ids - set(images))
    if missing:
        raise ValueError(f"missing RGBA images for layers: {', '.join(missing)}")

    selected: list[tuple[str, RgbaImage]] = []
    for layer in value.layers:
        image = images[layer.id]
        image.validate()
        if image.width + config.padding * 2 > config.max_size or image.height + config.padding * 2 > config.max_size:
            raise ValueError(
                f"layer {layer.id} ({image.width}x{image.height}) exceeds atlas max_size "
                f"{config.max_size} after padding"
            )
        selected.append((layer.id, image))

    ordered = tuple(sorted(selected, key=lambda item: (-item[1].height, -item[1].width, item[0])))
    area = sum(
        (image.width + config.padding * 2) * (image.height + config.padding * 2)
        for _, image in ordered
    )
    max_item_width = max(image.width + config.padding * 2 for _, image in ordered)
    width = _next_pow2(max(max_item_width, math.ceil(math.sqrt(area))))
    if width > config.max_size:
        raise ValueError("texture atlas exceeds configured maximum width")

    packed: tuple[list[AtlasPlacementV1], int] | None = None
    while width <= config.max_size:
        packed = _pack_shelves(ordered, width, config.padding, config.max_size)
        if packed is not None:
            break
        width *= 2
    if packed is None or width > config.max_size:
        raise ValueError(
            f"texture atlas cannot fit {len(ordered)} layers inside "
            f"{config.max_size}x{config.max_size}"
        )
    placements, used_height = packed
    height = _next_pow2(max(1, used_height))
    if height > config.max_size:
        raise ValueError("texture atlas exceeds configured maximum height")

    atlas = bytearray(width * height * 4)
    placement_by_id = {item.layer_id: item for item in placements}
    for layer_id, image in ordered:
        _copy_with_gutter(atlas, width, image, placement_by_id[layer_id], config.padding)
    return CompiledAtlasV1(width, height, bytes(atlas), tuple(sorted(placements, key=lambda item: item.layer_id)))


def _atlas_uv(point: Point2, placement: AtlasPlacementV1, atlas: CompiledAtlasV1) -> Point2:
    u = (placement.x + 0.5 + point.x * max(0, placement.width - 1)) / atlas.width
    v = (placement.y + 0.5 + point.y * max(0, placement.height - 1)) / atlas.height
    return Point2(u, v)


def _view(segment: _Segment, component_type: str, count: int, stride: int | None = None) -> dict[str, object]:
    out: dict[str, object] = {
        "buffer": "geometry", "byteOffset": segment.byte_offset,
        "byteLength": segment.byte_length, "componentType": component_type, "count": count,
    }
    if stride is not None:
        out["stride"] = stride
    return out


def _parameter(parameter_id: str) -> dict[str, object]:
    spec = _PARAMETER_SPEC.get(parameter_id)
    if spec is None:
        raise ValueError(f"missing parameter metadata for {parameter_id}")
    minimum, maximum, default = spec
    return {"id": parameter_id, "min": minimum, "max": maximum, "default": default}


def _linear_binding(binding) -> dict[str, object]:
    input_min, input_max = binding.input_range
    output_min, output_max = binding.output_range
    if input_max == input_min:
        raise ValueError(f"parameter binding {binding.parameter_id} has zero input range")
    scale = (output_max - output_min) / (input_max - input_min)
    return {"parameterId": binding.parameter_id, "scale": scale, "bias": output_min - input_min * scale}


def _head_data(proxy_z: ProxyZHeadPlanV1) -> dict[str, object]:
    data = proxy_z.data
    return {
        "pivot": [data.pivot[0], data.pivot[1]], "radius": [data.radius[0], data.radius[1]],
        "depthScale": data.depth_scale, "perspective": data.perspective,
        "yawGain": data.yaw_gain, "pitchGain": data.pitch_gain,
    }


def _deformers(
    rig: SemanticRigPlanV1, rig_plan: RigPlanV1, proxy_z: ProxyZHeadPlanV1,
) -> list[dict[str, object]]:
    head_targets = [part.id for part in rig_plan.parts if part.semantic in _HEAD_SEMANTICS]
    kind_map = {
        DeformerKind.WARP: "warp", DeformerKind.TRANSLATION: "warp",
        DeformerKind.ROTATION: "rotation", DeformerKind.MORPH: "morph",
        DeformerKind.PSEUDO3D_HEAD: "pseudo3d_head",
    }
    out: list[dict[str, object]] = []
    for rule in rig.deformers:
        item: dict[str, object] = {
            "id": rule.id, "type": kind_map[rule.kind],
            "targets": head_targets if rule.kind is DeformerKind.PSEUDO3D_HEAD else [rule.target_part_id],
            "parameterBindings": [_linear_binding(binding) for binding in rule.bindings],
        }
        if rule.parent_deformer_id is not None:
            item["parent"] = rule.parent_deformer_id
        if rule.kind is DeformerKind.PSEUDO3D_HEAD:
            item["data"] = _head_data(proxy_z)
        else:
            item["data"] = {
                "kind": rule.kind.value, "pivot": [rule.pivot.x, rule.pivot.y],
                "channels": [{
                    "parameterId": binding.parameter_id, "channel": binding.channel,
                    "inputRange": list(binding.input_range), "outputRange": list(binding.output_range),
                    "outputUnit": binding.output_unit,
                } for binding in rule.bindings],
            }
        out.append(item)
    return out


def _proxy_depths_for_part(
    semantic: Semantic, mesh: AdaptiveMesh, proxy_z: ProxyZHeadPlanV1,
) -> tuple[float, ...]:
    if semantic is Semantic.FACE:
        if len(proxy_z.proxy_z) != len(mesh.positions):
            raise ValueError("face proxy-Z count does not match face mesh during packing")
        return proxy_z.proxy_z
    if semantic not in _HEAD_SEMANTICS:
        return tuple(0.0 for _ in mesh.positions)
    center_x, center_y = proxy_z.profile_center
    radius_x, radius_y = proxy_z.data.radius
    bias_by_semantic = {item.semantic: item.bias for item in proxy_z.part_depth_biases}
    bias = bias_by_semantic.get(semantic, 0.0)
    values: list[float] = []
    for point in mesh.positions:
        dx = (point.x - center_x) / max(radius_x, 1e-12)
        dy = (point.y - center_y) / max(radius_y, 1e-12)
        radial = dx * dx + dy * dy
        base = 0.0 if radial >= 1.0 else max(0.0, 1.0 - radial) ** 0.65
        values.append(round(max(-0.25, min(1.25, base + bias)), 8))
    return tuple(values)


def _pack_points(points: tuple[Point2, ...]) -> bytes:
    return b"".join(struct.pack("<ff", point.x, point.y) for point in points)


def _pack_indices(mesh: AdaptiveMesh) -> tuple[bytes, str, int]:
    flat = [index for triangle in mesh.triangles for index in (triangle.a, triangle.b, triangle.c)]
    if len(mesh.positions) <= 0xFFFF:
        return b"".join(struct.pack("<H", index) for index in flat), "u16", len(flat)
    return b"".join(struct.pack("<I", index) for index in flat), "u32", len(flat)


def _morph_records_and_ranges(parts, meshes_by_layer, morph_plans):
    records: list = []
    ranges_by_part: dict[str, tuple[tuple[int, int], ...]] = {}
    for part in parts:
        mesh = meshes_by_layer[part.source_layer_id]
        plan = morph_plans.get(part.semantic)
        if plan is None:
            ranges_by_part[part.id] = tuple((len(records), 0) for _ in mesh.positions)
            continue
        base = len(records)
        records.extend(plan.records)
        ranges_by_part[part.id] = tuple((base + item.start, item.count) for item in plan.ranges)
    return records, ranges_by_part


def _build_model_and_geometry(
    value: NormalizedRigInput, rig_plan: RigPlanV1, semantic_rig: SemanticRigPlanV1,
    meshes_by_layer: Mapping[str, AdaptiveMesh], morph_plans: Mapping[Semantic, CompiledMorphPlanV1],
    proxy_z: ProxyZHeadPlanV1, physics: AutoPhysicsPlanV1, atlas: CompiledAtlasV1,
) -> tuple[dict[str, object], bytes]:
    builder = _BinaryBuilder()
    placement_by_id = {item.layer_id: item for item in atlas.placements}
    records, ranges_by_part = _morph_records_and_ranges(rig_plan.parts, meshes_by_layer, morph_plans)
    parts: list[dict[str, object]] = []

    for planned in rig_plan.parts:
        mesh = meshes_by_layer[planned.source_layer_id]
        placement = placement_by_id[planned.source_layer_id]
        atlas_uvs = tuple(_atlas_uv(point, placement, atlas) for point in mesh.uvs)
        proxy_depths = _proxy_depths_for_part(planned.semantic, mesh, proxy_z)
        positions_segment = builder.append(_pack_points(mesh.positions))
        uvs_segment = builder.append(_pack_points(atlas_uvs))
        proxy_segment = builder.append(b"".join(struct.pack("<f", depth) for depth in proxy_depths))
        range_segment = builder.append(b"".join(
            struct.pack("<II", start, count) for start, count in ranges_by_part[planned.id]
        ))
        index_bytes, index_component, index_count = _pack_indices(mesh)
        index_segment = builder.append(index_bytes)
        part: dict[str, object] = {
            "id": planned.id, "name": planned.source_layer_id, "semantic": _PART_SEMANTIC[planned.semantic],
            "parent": planned.parent, "drawOrder": planned.draw_order,
            "material": {"textureId": "atlas0", "opacity": 1.0, "blendMode": "normal"},
            "mesh": {
                "positions": _view(positions_segment, "f32", len(mesh.positions), 8),
                "uvs": _view(uvs_segment, "f32", len(mesh.uvs), 8),
                "indices": _view(index_segment, index_component, index_count),
                "proxyZ": _view(proxy_segment, "f32", len(mesh.positions), 4),
                "influenceRanges": _view(range_segment, "u32", len(mesh.positions), 8),
            },
        }
        if planned.semantic is Semantic.IRIS_L:
            part["clip"] = {"sources": ["eye-white-l"], "mode": "inside"}
        elif planned.semantic is Semantic.IRIS_R:
            part["clip"] = {"sources": ["eye-white-r"], "mode": "inside"}
        parts.append(part)

    morph_payload = bytearray()
    for record in records:
        morph_payload.extend(struct.pack(
            "<Ifff", record.parameter_index, record.delta_x, record.delta_y, record.weight,
        ))
    morph_segment = builder.append(bytes(morph_payload))
    geometry = builder.finish()

    model: dict[str, object] = {
        "formatVersion": 1, "id": value.character_id, "name": value.character_id,
        "canvas": {"width": value.canvas_width, "height": value.canvas_height},
        "buffers": [{"id": "geometry", "uri": "buffers/geometry.bin", "byteLength": len(geometry)}],
        "textures": [{
            "id": "atlas0", "uri": "textures/atlas0.rgba", "byteLength": len(atlas.pixels),
            "format": "rgba8", "width": atlas.width, "height": atlas.height,
            "alphaMode": "straight", "filter": "linear",
        }],
        "parameters": [_parameter(parameter_id) for parameter_id in rig_plan.parameter_ids],
        "parts": parts, "deformers": _deformers(semantic_rig, rig_plan, proxy_z),
        "deformationBuffers": {"morphInfluences": {"view": {
            "buffer": "geometry", "byteOffset": morph_segment.byte_offset,
            "byteLength": morph_segment.byte_length, "count": len(records), "stride": 16,
        }, "strideBytes": 16}},
        "physics": [chain.runtime.to_avatar_ir() for chain in physics.chains],
        "expressions": [{
            "id": expression.id,
            "bindings": [{"parameterId": binding.parameter_id, "mode": binding.mode, "value": binding.value}
                         for binding in expression.bindings],
        } for expression in rig_plan.expressions],
    }
    return model, geometry


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _build_a2d(files: Mapping[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[path])
    return output.getvalue()


def _findings_report(
    character_id: str, findings: tuple[CompileQaFindingV1, ...], config: CompileQaConfig,
) -> CompileQaReportV1:
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    unique = {(item.severity, item.stage.value, item.code, item.message, item.subject_id): item for item in findings}
    ordered = tuple(sorted(unique.values(), key=lambda item: (
        severity_rank.get(item.severity, 3), list(QaStage).index(item.stage), item.code,
        item.subject_id or "", item.message,
    )))
    errors = sum(item.severity == "error" for item in ordered)
    warnings = sum(item.severity == "warning" for item in ordered)
    infos = sum(item.severity == "info" for item in ordered)
    score = max(0, min(100, 100 - errors * config.error_penalty - warnings * config.warning_penalty))
    stages = tuple(StageQaSummaryV1(
        stage,
        sum(item.stage is stage and item.severity == "error" for item in ordered),
        sum(item.stage is stage and item.severity == "warning" for item in ordered),
        sum(item.stage is stage and item.severity == "info" for item in ordered),
    ) for stage in QaStage)
    return CompileQaReportV1(1, character_id, errors == 0, score, errors, warnings, infos, ordered, stages)


def _failure(
    character_id: str, stage: QaStage, code: str, message: str, subject_id: str | None,
    config: CompileQaConfig, base: CompileQaReportV1 | None = None,
) -> OneClickCompileResultV1:
    findings = list(base.findings if base is not None else ())
    findings.append(CompileQaFindingV1("error", stage, code, message, subject_id))
    return OneClickCompileResultV1(1, character_id, _findings_report(character_id, tuple(findings), config), None)


def compile_avatar(
    value: NormalizedRigInput, masks: Mapping[str, AlphaMask], images: Mapping[str, RgbaImage], *,
    qa_config: CompileQaConfig | None = None, atlas_config: AtlasConfig | None = None,
) -> OneClickCompileResultV1:
    """Run P2-R1..R8 and emit a deterministic .a2d package only when QA is ready."""
    qa_config = qa_config or CompileQaConfig()
    qa_config.validate()
    character_id = value.character_id or "<invalid>"

    try:
        rig_plan = compile_rig_plan(value)
    except (ValueError, TypeError) as exc:
        return _failure(character_id, QaStage.CONTRACT, "compile-contract-failed", str(exc), None, qa_config)

    meshes_by_layer: dict[str, AdaptiveMesh] = {}
    meshes_by_semantic: dict[Semantic, AdaptiveMesh] = {}
    mesh_failures: list[CompileQaFindingV1] = []
    for layer in sorted(value.layers, key=lambda item: item.id):
        mask = masks.get(layer.id)
        if mask is None:
            mesh_failures.append(CompileQaFindingV1(
                "error", QaStage.MESH, "compile-mask-missing", f"missing alpha mask for layer {layer.id}", layer.id,
            ))
            continue
        image = images.get(layer.id)
        if image is None:
            mesh_failures.append(CompileQaFindingV1(
                "error", QaStage.CROSS_STAGE, "compile-image-missing", f"missing RGBA image for layer {layer.id}", layer.id,
            ))
            continue
        try:
            image.validate()
            mask.validate()
            if image.width != mask.width or image.height != mask.height:
                raise ValueError(
                    f"image/mask dimensions differ for {layer.id}: "
                    f"{image.width}x{image.height} vs {mask.width}x{mask.height}"
                )
            mesh = generate_layer_mesh(layer, mask, value.landmarks)
        except (ValueError, TypeError, MeshGenerationError) as exc:
            mesh_failures.append(CompileQaFindingV1(
                "error", QaStage.MESH, "compile-mesh-failed", str(exc), layer.id,
            ))
            continue
        meshes_by_layer[layer.id] = mesh
        if layer.semantic is not Semantic.ACCESSORY:
            meshes_by_semantic[layer.semantic] = mesh
    if mesh_failures:
        return OneClickCompileResultV1(1, character_id, _findings_report(character_id, tuple(mesh_failures), qa_config), None)

    try:
        semantic_rig = compile_semantic_rig(value, rig_plan)
    except (ValueError, TypeError) as exc:
        return _failure(character_id, QaStage.SEMANTIC_RIG, "compile-semantic-rig-failed", str(exc), None, qa_config)

    try:
        proxy_z = compile_proxy_z_head(value, meshes_by_semantic[Semantic.FACE], semantic_rig)
    except (KeyError, ValueError, TypeError) as exc:
        return _failure(character_id, QaStage.PROXY_Z, "compile-proxy-z-failed", str(exc), "face", qa_config)

    part_semantic = {part.id: part.semantic for part in rig_plan.parts}
    morph_semantics = sorted({
        part_semantic[intent.target_part_id] for intent in semantic_rig.morph_intents
        if intent.target_part_id in part_semantic
    }, key=lambda item: item.value)
    morph_plans: dict[Semantic, CompiledMorphPlanV1] = {}
    try:
        for semantic in morph_semantics:
            morph_plans[semantic] = compile_semantic_morphs(
                value, semantic, meshes_by_semantic[semantic], rig_plan, semantic_rig,
            )
    except (KeyError, ValueError, TypeError) as exc:
        return _failure(character_id, QaStage.MORPH, "compile-morph-failed", str(exc), None, qa_config)

    try:
        physics = compile_auto_physics(value, meshes_by_semantic, rig_plan, semantic_rig)
    except (KeyError, ValueError, TypeError) as exc:
        return _failure(character_id, QaStage.PHYSICS, "compile-physics-failed", str(exc), None, qa_config)

    qa = compile_qa_report(
        value, meshes_by_semantic, rig_plan, semantic_rig, proxy_z, morph_plans, physics,
        config=qa_config,
    )
    if not qa.ready:
        return OneClickCompileResultV1(1, character_id, qa, None)

    try:
        atlas = build_texture_atlas(value, images, config=atlas_config)
        model, geometry = _build_model_and_geometry(
            value, rig_plan, semantic_rig, meshes_by_layer, morph_plans, proxy_z, physics, atlas,
        )
        qa_json = _canonical_json(qa.to_dict())
        manifest: dict[str, object] = {
            "containerVersion": 1, "model": "model.json", "entryBuffers": ["buffers/geometry.bin"],
        }
        files = {
            "manifest.json": _canonical_json(manifest), "model.json": _canonical_json(model),
            "buffers/geometry.bin": geometry, "textures/atlas0.rgba": atlas.pixels,
            "qa/report.json": qa_json,
        }
        package = _build_a2d(files)
    except (ValueError, TypeError, KeyError, struct.error) as exc:
        return _failure(
            character_id, QaStage.CROSS_STAGE, "compile-package-failed", str(exc), None, qa_config, qa,
        )

    artifact = CompiledAvatarArtifactV1(
        manifest, model, geometry, atlas, qa_json, package, hashlib.sha256(package).hexdigest(),
    )
    return OneClickCompileResultV1(1, character_id, qa, artifact)
