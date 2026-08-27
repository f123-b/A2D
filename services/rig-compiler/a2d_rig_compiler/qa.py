from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
from typing import Mapping

from .adaptive_mesh import AdaptiveMesh
from .auto_physics import AutoPhysicsPlanV1
from .contract import NormalizedRigInput, QaFinding, RigPlanV1, Semantic
from .facial_morph import CompiledMorphPlanV1
from .proxy_z import ProxyZHeadPlanV1
from .semantic_rig import SemanticRigPlanV1


class QaStage(StrEnum):
    CONTRACT = "contract"
    MESH = "mesh"
    SEMANTIC_RIG = "semantic_rig"
    PROXY_Z = "proxy_z"
    MORPH = "morph"
    PHYSICS = "physics"
    CROSS_STAGE = "cross_stage"


@dataclass(frozen=True, slots=True, order=True)
class CompileQaFindingV1:
    severity: str
    stage: QaStage
    code: str
    message: str
    subject_id: str | None = None


@dataclass(frozen=True, slots=True)
class StageQaSummaryV1:
    stage: QaStage
    errors: int
    warnings: int
    infos: int


@dataclass(frozen=True, slots=True)
class CompileQaReportV1:
    version: int
    character_id: str
    ready: bool
    score: int
    errors: int
    warnings: int
    infos: int
    findings: tuple[CompileQaFindingV1, ...]
    stages: tuple[StageQaSummaryV1, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "characterId": self.character_id,
            "ready": self.ready,
            "score": self.score,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos,
            "findings": [
                {
                    "severity": item.severity,
                    "stage": item.stage.value,
                    "code": item.code,
                    "message": item.message,
                    **({"subjectId": item.subject_id} if item.subject_id is not None else {}),
                }
                for item in self.findings
            ],
            "stages": [
                {
                    "stage": item.stage.value,
                    "errors": item.errors,
                    "warnings": item.warnings,
                    "infos": item.infos,
                }
                for item in self.stages
            ],
        }


@dataclass(frozen=True, slots=True)
class CompileQaConfig:
    mesh_coverage_error_threshold: float = 0.45
    mesh_min_angle_error_degrees: float = 1.99
    min_proxy_z: float = -0.25
    max_proxy_z: float = 1.25
    max_morph_influences_per_vertex: int = 8
    error_penalty: int = 25
    warning_penalty: int = 4

    def validate(self) -> None:
        if not 0 <= self.mesh_coverage_error_threshold <= 1:
            raise ValueError("mesh_coverage_error_threshold must be 0..1")
        if not 0 <= self.mesh_min_angle_error_degrees <= 180:
            raise ValueError("mesh_min_angle_error_degrees must be 0..180")
        if not math.isfinite(self.min_proxy_z) or not math.isfinite(self.max_proxy_z) or self.min_proxy_z >= self.max_proxy_z:
            raise ValueError("proxy-Z QA range must be finite with min < max")
        if not 1 <= self.max_morph_influences_per_vertex <= 8:
            raise ValueError("max_morph_influences_per_vertex must be 1..8")
        if self.error_penalty < 0 or self.warning_penalty < 0:
            raise ValueError("QA penalties must be >= 0")


_STAGE_ORDER: tuple[QaStage, ...] = tuple(QaStage)


def _normalize_severity(value: str) -> str:
    if value in {"error", "warning", "info"}:
        return value
    return "error"


def _append_source_findings(
    out: list[CompileQaFindingV1],
    stage: QaStage,
    findings: tuple[QaFinding, ...],
) -> None:
    for finding in findings:
        out.append(CompileQaFindingV1(
            _normalize_severity(finding.severity),
            stage,
            finding.code,
            finding.message,
            finding.layer_id,
        ))


def _error(
    out: list[CompileQaFindingV1],
    stage: QaStage,
    code: str,
    message: str,
    subject_id: str | None = None,
) -> None:
    out.append(CompileQaFindingV1("error", stage, code, message, subject_id))


def _validate_meshes(
    meshes: Mapping[Semantic, AdaptiveMesh],
    rig_plan: RigPlanV1,
    config: CompileQaConfig,
    out: list[CompileQaFindingV1],
) -> None:
    required_semantics = {
        part.semantic
        for part in rig_plan.parts
        if part.semantic is not Semantic.ACCESSORY
    }
    for semantic in sorted(required_semantics, key=lambda item: item.value):
        mesh = meshes.get(semantic)
        if mesh is None:
            _error(out, QaStage.MESH, "mesh-missing", f"missing compiled mesh for {semantic.value}", semantic.value)
            continue
        count = len(mesh.positions)
        if count < 3:
            _error(out, QaStage.MESH, "mesh-too-small", f"{semantic.value} has only {count} vertices", semantic.value)
        if len(mesh.uvs) != count:
            _error(out, QaStage.MESH, "mesh-uv-count-mismatch", f"{semantic.value} UV count does not match vertex count", semantic.value)
        if mesh.quality.vertex_count != count:
            _error(out, QaStage.MESH, "mesh-quality-count-mismatch", f"{semantic.value} quality vertex count is stale", semantic.value)
        if mesh.quality.coverage_ratio < config.mesh_coverage_error_threshold:
            _error(out, QaStage.MESH, "mesh-coverage-too-low", f"{semantic.value} coverage {mesh.quality.coverage_ratio:.3f} is below {config.mesh_coverage_error_threshold:.3f}", semantic.value)
        if mesh.triangles and mesh.quality.min_angle_degrees < config.mesh_min_angle_error_degrees:
            _error(out, QaStage.MESH, "mesh-angle-too-small", f"{semantic.value} minimum angle {mesh.quality.min_angle_degrees:.3f}° is below hard QA threshold", semantic.value)
        if any(not math.isfinite(point.x) or not math.isfinite(point.y) for point in mesh.positions):
            _error(out, QaStage.MESH, "mesh-nonfinite-position", f"{semantic.value} contains a non-finite position", semantic.value)
        if any(
            min(triangle.a, triangle.b, triangle.c) < 0
            or max(triangle.a, triangle.b, triangle.c) >= count
            for triangle in mesh.triangles
        ):
            _error(out, QaStage.MESH, "mesh-index-out-of-range", f"{semantic.value} triangle index is out of range", semantic.value)
        for finding in mesh.quality.findings:
            out.append(CompileQaFindingV1(
                _normalize_severity(finding.severity),
                QaStage.MESH,
                finding.code,
                finding.message,
                semantic.value,
            ))

    if any(part.semantic is Semantic.ACCESSORY for part in rig_plan.parts):
        out.append(CompileQaFindingV1(
            "info",
            QaStage.MESH,
            "accessory-mesh-not-assessed-by-semantic-map",
            "accessory meshes require source-layer keyed QA in the future multi-accessory compiler path",
        ))


def _validate_proxy_z(
    meshes: Mapping[Semantic, AdaptiveMesh],
    rig_plan: RigPlanV1,
    proxy_z: ProxyZHeadPlanV1 | None,
    character_id: str,
    config: CompileQaConfig,
    out: list[CompileQaFindingV1],
) -> None:
    if proxy_z is None:
        _error(out, QaStage.PROXY_Z, "proxy-z-missing", "missing P2-R4 proxy-Z output", "face")
        return
    if proxy_z.character_id != character_id:
        _error(out, QaStage.CROSS_STAGE, "character-id-mismatch", "proxy-Z character_id does not match compiler input", "proxy_z")
    expected_face = next((part.id for part in rig_plan.parts if part.semantic is Semantic.FACE), None)
    if expected_face is None or proxy_z.face_part_id != expected_face:
        _error(out, QaStage.PROXY_Z, "proxy-z-face-part-mismatch", f"proxy-Z target {proxy_z.face_part_id} does not match canonical face part {expected_face}", "face")
    face = meshes.get(Semantic.FACE)
    if face is not None and len(proxy_z.proxy_z) != len(face.positions):
        _error(out, QaStage.PROXY_Z, "proxy-z-count-mismatch", f"proxy-Z count {len(proxy_z.proxy_z)} does not match face vertex count {len(face.positions)}", "face")
    if not proxy_z.proxy_z:
        _error(out, QaStage.PROXY_Z, "proxy-z-empty", "proxy-Z output is empty", "face")
    elif any(
        not math.isfinite(value)
        or value < config.min_proxy_z
        or value > config.max_proxy_z
        for value in proxy_z.proxy_z
    ):
        _error(out, QaStage.PROXY_Z, "proxy-z-out-of-range", f"proxy-Z values must remain in [{config.min_proxy_z:.2f},{config.max_proxy_z:.2f}]", "face")
    data = proxy_z.data
    numeric = (*data.pivot, *data.radius, data.depth_scale, data.perspective, data.yaw_gain, data.pitch_gain)
    if any(not math.isfinite(value) for value in numeric) or min(data.radius) <= 0 or data.depth_scale <= 0:
        _error(out, QaStage.PROXY_Z, "proxy-z-head-data-invalid", "Pseudo3D head metadata is non-finite or non-positive", "face")
    _append_source_findings(out, QaStage.PROXY_Z, proxy_z.findings)


def _validate_morphs(
    meshes: Mapping[Semantic, AdaptiveMesh],
    rig_plan: RigPlanV1,
    semantic_rig: SemanticRigPlanV1,
    morph_plans: Mapping[Semantic, CompiledMorphPlanV1],
    config: CompileQaConfig,
    out: list[CompileQaFindingV1],
) -> None:
    part_by_id = {part.id: part for part in rig_plan.parts}
    parameter_index = {parameter_id: index for index, parameter_id in enumerate(rig_plan.parameter_ids)}
    intents_by_semantic: dict[Semantic, list] = {}
    for intent in semantic_rig.morph_intents:
        part = part_by_id.get(intent.target_part_id)
        if part is None:
            _error(out, QaStage.CROSS_STAGE, "morph-intent-target-missing", f"morph intent {intent.id} targets unknown part {intent.target_part_id}", intent.id)
            continue
        intents_by_semantic.setdefault(part.semantic, []).append(intent)

    for semantic in sorted(intents_by_semantic, key=lambda item: item.value):
        intents = sorted(intents_by_semantic[semantic], key=lambda item: item.id)
        part = next((item for item in rig_plan.parts if item.semantic is semantic), None)
        plan = morph_plans.get(semantic)
        if plan is None:
            _error(out, QaStage.MORPH, "morph-plan-missing", f"missing morph plan for {semantic.value}", semantic.value)
            continue
        mesh = meshes.get(semantic)
        if mesh is None:
            continue
        if plan.semantic is not semantic:
            _error(out, QaStage.MORPH, "morph-semantic-mismatch", f"morph plan semantic does not match {semantic.value}", semantic.value)
        if part is None or plan.target_part_id != part.id:
            _error(out, QaStage.MORPH, "morph-target-part-mismatch", f"morph target {plan.target_part_id} does not match canonical part {part.id if part else None}", semantic.value)
        actual_intent_ids = {record.intent_id for record in plan.records}
        for intent in intents:
            if intent.id not in actual_intent_ids:
                _error(out, QaStage.MORPH, "morph-intent-empty", f"morph intent {intent.id} produced no Runtime influence records", semantic.value)
        expected_intent_ids = {intent.id for intent in intents}
        for record in plan.records:
            if record.intent_id not in expected_intent_ids:
                _error(out, QaStage.MORPH, "morph-record-unplanned-intent", f"{semantic.value} contains record for unplanned intent {record.intent_id}", semantic.value)
                break
        if len(plan.ranges) != len(mesh.positions):
            _error(out, QaStage.MORPH, "morph-range-count-mismatch", f"{semantic.value} has {len(plan.ranges)} ranges for {len(mesh.positions)} vertices", semantic.value)
            continue
        expected_start = 0
        for vertex_index, vertex_range in enumerate(plan.ranges):
            if vertex_range.start != expected_start:
                _error(out, QaStage.MORPH, "morph-range-not-contiguous", f"{semantic.value} vertex {vertex_index} range does not continue from prior records", semantic.value)
            if vertex_range.start < 0 or vertex_range.count < 0 or vertex_range.start + vertex_range.count > len(plan.records):
                _error(out, QaStage.MORPH, "morph-range-out-of-bounds", f"{semantic.value} vertex {vertex_index} influence range is invalid", semantic.value)
                continue
            if vertex_range.count > config.max_morph_influences_per_vertex:
                _error(out, QaStage.MORPH, "morph-influence-limit", f"{semantic.value} vertex {vertex_index} has {vertex_range.count} influences; Runtime v1 limit is {config.max_morph_influences_per_vertex}", semantic.value)
            for record in plan.records[vertex_range.start:vertex_range.start + vertex_range.count]:
                if record.vertex_index != vertex_index:
                    _error(out, QaStage.MORPH, "morph-range-vertex-mismatch", f"{semantic.value} range points to record for another vertex", semantic.value)
                    break
            expected_start = vertex_range.start + vertex_range.count
        if expected_start != len(plan.records):
            _error(out, QaStage.MORPH, "morph-records-uncovered", f"{semantic.value} ranges do not cover every influence record", semantic.value)
        intent_by_id = {intent.id: intent for intent in intents}
        for record in plan.records:
            if record.parameter_index < 0 or record.parameter_index >= len(rig_plan.parameter_ids):
                _error(out, QaStage.MORPH, "morph-parameter-index-out-of-range", f"{semantic.value} has parameter index {record.parameter_index} outside parameter table", semantic.value)
                break
            intent = intent_by_id.get(record.intent_id)
            if intent is not None and parameter_index.get(intent.parameter_id) != record.parameter_index:
                _error(out, QaStage.MORPH, "morph-parameter-binding-mismatch", f"record for {record.intent_id} uses parameter index {record.parameter_index} instead of {parameter_index.get(intent.parameter_id)}", semantic.value)
                break
            if not all(math.isfinite(value) for value in (record.delta_x, record.delta_y, record.weight)) or not 0 <= record.weight <= 1:
                _error(out, QaStage.MORPH, "morph-invalid-record", f"{semantic.value} contains non-finite delta/weight or weight outside [0,1]", semantic.value)
                break
        _append_source_findings(out, QaStage.MORPH, plan.findings)


def _validate_physics(
    rig_plan: RigPlanV1,
    physics: AutoPhysicsPlanV1 | None,
    character_id: str,
    out: list[CompileQaFindingV1],
) -> None:
    if physics is None:
        if rig_plan.physics:
            _error(out, QaStage.PHYSICS, "physics-plan-missing", "hair physics rules exist but P2-R6 output is missing")
        return
    if physics.character_id != character_id:
        _error(out, QaStage.CROSS_STAGE, "character-id-mismatch", "physics character_id does not match compiler input", "physics")
    rules = {rule.id: rule for rule in rig_plan.physics}
    chains = {chain.runtime.id: chain for chain in physics.chains}
    for missing in sorted(set(rules) - set(chains)):
        _error(out, QaStage.PHYSICS, "physics-chain-missing", f"missing compiled physics chain: {missing}", missing)
    for extra in sorted(set(chains) - set(rules)):
        _error(out, QaStage.PHYSICS, "physics-chain-unplanned", f"compiled physics chain is not present in RigPlan: {extra}", extra)
    parameter_ids = set(rig_plan.parameter_ids)
    for chain_id, chain in sorted(chains.items()):
        runtime = chain.runtime
        rule = rules.get(chain_id)
        if rule is not None:
            if chain.source_part_id != rule.source_part_id:
                _error(out, QaStage.PHYSICS, "physics-source-part-mismatch", f"{runtime.id} source part {chain.source_part_id} does not match RigPlan {rule.source_part_id}", runtime.id)
            outputs = {binding.parameter_id for binding in runtime.output_bindings}
            if rule.output_parameter not in outputs:
                _error(out, QaStage.PHYSICS, "physics-output-binding-mismatch", f"{runtime.id} does not output planned parameter {rule.output_parameter}", runtime.id)
        if runtime.node_count < 2 or not math.isfinite(runtime.segment_length) or runtime.segment_length <= 0:
            _error(out, QaStage.PHYSICS, "physics-chain-invalid-shape", f"{runtime.id} nodeCount/segmentLength is invalid", runtime.id)
        if not 0 <= runtime.damping <= 1 or not 0 <= runtime.stiffness <= 1:
            _error(out, QaStage.PHYSICS, "physics-chain-invalid-dynamics", f"{runtime.id} damping/stiffness is outside [0,1]", runtime.id)
        for binding in (*runtime.input_bindings, *runtime.output_bindings):
            if binding.parameter_id not in parameter_ids:
                _error(out, QaStage.PHYSICS, "physics-parameter-missing", f"{runtime.id} references missing parameter {binding.parameter_id}", runtime.id)
    _append_source_findings(out, QaStage.PHYSICS, physics.findings)


def compile_qa_report(
    value: NormalizedRigInput,
    meshes: Mapping[Semantic, AdaptiveMesh],
    rig_plan: RigPlanV1,
    semantic_rig: SemanticRigPlanV1,
    proxy_z: ProxyZHeadPlanV1 | None,
    morph_plans: Mapping[Semantic, CompiledMorphPlanV1],
    physics: AutoPhysicsPlanV1 | None,
    *,
    config: CompileQaConfig | None = None,
) -> CompileQaReportV1:
    """Aggregate P2-R1..R6 outputs into the single P2-R7 compile-readiness gate."""
    config = config or CompileQaConfig()
    config.validate()
    out: list[CompileQaFindingV1] = []

    if rig_plan.character_id != value.character_id:
        _error(out, QaStage.CROSS_STAGE, "character-id-mismatch", "RigPlan character_id does not match compiler input", "rig_plan")
    if semantic_rig.character_id != value.character_id:
        _error(out, QaStage.CROSS_STAGE, "character-id-mismatch", "SemanticRig character_id does not match compiler input", "semantic_rig")

    _append_source_findings(out, QaStage.CONTRACT, rig_plan.findings)
    _append_source_findings(out, QaStage.SEMANTIC_RIG, semantic_rig.findings)
    _validate_meshes(meshes, rig_plan, config, out)
    _validate_proxy_z(meshes, rig_plan, proxy_z, value.character_id, config, out)
    _validate_morphs(meshes, rig_plan, semantic_rig, morph_plans, config, out)
    _validate_physics(rig_plan, physics, value.character_id, out)

    unique = {
        (item.severity, item.stage.value, item.code, item.message, item.subject_id): item
        for item in out
    }
    findings = tuple(sorted(
        unique.values(),
        key=lambda item: (
            {"error": 0, "warning": 1, "info": 2}.get(item.severity, 3),
            _STAGE_ORDER.index(item.stage),
            item.code,
            item.subject_id or "",
            item.message,
        ),
    ))

    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    infos = sum(item.severity == "info" for item in findings)
    score = max(0, min(100, 100 - errors * config.error_penalty - warnings * config.warning_penalty))
    stages = tuple(
        StageQaSummaryV1(
            stage,
            sum(item.stage is stage and item.severity == "error" for item in findings),
            sum(item.stage is stage and item.severity == "warning" for item in findings),
            sum(item.stage is stage and item.severity == "info" for item in findings),
        )
        for stage in _STAGE_ORDER
    )
    return CompileQaReportV1(
        1,
        value.character_id,
        errors == 0,
        score,
        errors,
        warnings,
        infos,
        findings,
        stages,
    )
