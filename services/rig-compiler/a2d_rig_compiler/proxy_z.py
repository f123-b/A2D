from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct
from typing import Iterable

from .adaptive_mesh import AdaptiveMesh, Point2, Triangle
from .contract import Landmark, NormalizedRigInput, QaFinding, Semantic, SemanticLayer
from .semantic_rig import DeformerKind, SemanticRigPlanV1, compile_semantic_rig

_EPS = 1e-12


@dataclass(frozen=True, slots=True)
class ProxyZConfig:
    radial_exponent: float = 0.65
    smoothing_iterations: int = 2
    smoothing_strength: float = 0.28
    depth_scale_ratio: float = 0.55
    perspective: float = 1.10
    yaw_gain: float = 1.0
    pitch_gain: float = 1.0
    min_landmark_confidence: float = 0.5

    def validate(self) -> None:
        if not 0.1 <= self.radial_exponent <= 2.0:
            raise ValueError("radial_exponent must be 0.1..2")
        if not 0 <= self.smoothing_iterations <= 16:
            raise ValueError("smoothing_iterations must be 0..16")
        if not 0 <= self.smoothing_strength <= 1:
            raise ValueError("smoothing_strength must be 0..1")
        if not 0.05 <= self.depth_scale_ratio <= 2.0:
            raise ValueError("depth_scale_ratio must be 0.05..2")
        if not 0 <= self.perspective <= 4:
            raise ValueError("perspective must be 0..4")
        if self.yaw_gain <= 0 or self.pitch_gain <= 0:
            raise ValueError("gains must be positive")
        if not 0 <= self.min_landmark_confidence <= 1:
            raise ValueError("min_landmark_confidence must be 0..1")


@dataclass(frozen=True, slots=True)
class Pseudo3DHeadDataV1:
    pivot: tuple[float, float]
    radius: tuple[float, float]
    depth_scale: float
    perspective: float
    yaw_gain: float
    pitch_gain: float


@dataclass(frozen=True, slots=True)
class DepthFeatureRule:
    id: str
    landmark_id: str
    strength: float
    sigma_x: float
    sigma_y: float


@dataclass(frozen=True, slots=True)
class PartDepthBiasRule:
    semantic: Semantic
    bias: float


@dataclass(frozen=True, slots=True)
class ProxyZHeadPlanV1:
    version: int
    character_id: str
    face_part_id: str
    profile_center: tuple[float, float]
    proxy_z: tuple[float, ...]
    data: Pseudo3DHeadDataV1
    depth_features: tuple[DepthFeatureRule, ...]
    part_depth_biases: tuple[PartDepthBiasRule, ...]
    findings: tuple[QaFinding, ...] = field(default_factory=tuple)


_FEATURE_SPECS: tuple[tuple[str, tuple[str, ...], float, float, float], ...] = (
    ("nose", ("nose", "nose_tip"), 0.24, 0.18, 0.22),
    ("cheek-l", ("cheek_l", "left_cheek"), 0.07, 0.22, 0.20),
    ("cheek-r", ("cheek_r", "right_cheek"), 0.07, 0.22, 0.20),
    ("eye-l", ("eye_l_center", "left_eye_center"), 0.035, 0.16, 0.14),
    ("eye-r", ("eye_r_center", "right_eye_center"), 0.035, 0.16, 0.14),
    ("mouth", ("mouth_center",), 0.025, 0.20, 0.16),
    ("ear-l", ("ear_l", "left_ear"), -0.10, 0.18, 0.24),
    ("ear-r", ("ear_r", "right_ear"), -0.10, 0.18, 0.24),
)

_PART_DEPTH_BIASES: tuple[PartDepthBiasRule, ...] = (
    PartDepthBiasRule(Semantic.HAIR_FRONT, 0.18),
    PartDepthBiasRule(Semantic.HAIR_SIDE_L, 0.03),
    PartDepthBiasRule(Semantic.HAIR_SIDE_R, 0.03),
    PartDepthBiasRule(Semantic.HAIR_BACK, -0.20),
)


def _landmarks(value: NormalizedRigInput) -> dict[str, Landmark]:
    out: dict[str, Landmark] = {}
    for landmark in value.landmarks:
        landmark.validate()
        if landmark.id in out:
            raise ValueError(f"duplicate landmark id: {landmark.id}")
        out[landmark.id] = landmark
    return out


def _find_landmark(
    table: dict[str, Landmark], aliases: Iterable[str], threshold: float
) -> Landmark | None:
    for name in aliases:
        landmark = table.get(name)
        if landmark is not None and landmark.confidence >= threshold:
            return landmark
    return None


def _face_layer(value: NormalizedRigInput) -> SemanticLayer:
    faces = [layer for layer in value.layers if layer.semantic is Semantic.FACE]
    if len(faces) != 1:
        raise ValueError(f"expected exactly one face layer, got {len(faces)}")
    return faces[0]


def _head_rule(rig: SemanticRigPlanV1):
    rules = [
        deformer
        for deformer in rig.deformers
        if deformer.kind is DeformerKind.PSEUDO3D_HEAD or deformer.id == "head-pseudo3d"
    ]
    if len(rules) != 1:
        raise ValueError(f"expected exactly one pseudo3d head deformer, got {len(rules)}")
    return rules[0]


def _profile_center(
    face: SemanticLayer, table: dict[str, Landmark], threshold: float
) -> tuple[float, float]:
    landmark = _find_landmark(table, ("face_center", "head_center"), threshold)
    if landmark:
        return (landmark.x, landmark.y)
    return (
        face.bbox.x + face.bbox.width * 0.5,
        face.bbox.y + face.bbox.height * 0.48,
    )


def _estimate_radius(
    face: SemanticLayer, table: dict[str, Landmark], threshold: float
) -> tuple[float, float]:
    radius_x = face.bbox.width * 0.50
    radius_y = face.bbox.height * 0.50
    left = _find_landmark(table, ("eye_l_center", "left_eye_center"), threshold)
    right = _find_landmark(table, ("eye_r_center", "right_eye_center"), threshold)
    if left and right:
        eye_distance = math.hypot(right.x - left.x, right.y - left.y)
        radius_x = max(
            face.bbox.width * 0.44,
            min(face.bbox.width * 0.60, eye_distance * 1.35),
        )
    return (max(radius_x, _EPS), max(radius_y, _EPS))


def _base_depth(
    point: Point2,
    center: tuple[float, float],
    radius: tuple[float, float],
    exponent: float,
) -> float:
    dx = (point.x - center[0]) / radius[0]
    dy = (point.y - center[1]) / radius[1]
    radial = dx * dx + dy * dy
    if radial >= 1:
        return 0.0
    return max(0.0, 1.0 - radial) ** exponent


def _gaussian_bias(
    point: Point2,
    landmark: Landmark,
    radius: tuple[float, float],
    strength: float,
    sigma_x: float,
    sigma_y: float,
) -> float:
    dx = (point.x - landmark.x) / max(_EPS, radius[0] * sigma_x)
    dy = (point.y - landmark.y) / max(_EPS, radius[1] * sigma_y)
    return strength * math.exp(-0.5 * (dx * dx + dy * dy))


def _boundary_vertices(triangles: tuple[Triangle, ...]) -> set[int]:
    counts: dict[tuple[int, int], int] = {}
    for triangle in triangles:
        for u, v in (
            (triangle.a, triangle.b),
            (triangle.b, triangle.c),
            (triangle.c, triangle.a),
        ):
            edge = (u, v) if u < v else (v, u)
            counts[edge] = counts.get(edge, 0) + 1
    return {index for edge, count in counts.items() if count == 1 for index in edge}


def _adjacency(
    vertex_count: int, triangles: tuple[Triangle, ...]
) -> tuple[tuple[int, ...], ...]:
    adjacency = [set() for _ in range(vertex_count)]
    for triangle in triangles:
        for a, b in (
            (triangle.a, triangle.b),
            (triangle.b, triangle.c),
            (triangle.c, triangle.a),
        ):
            if 0 <= a < vertex_count and 0 <= b < vertex_count:
                adjacency[a].add(b)
                adjacency[b].add(a)
    return tuple(tuple(sorted(neighbors)) for neighbors in adjacency)


def _smooth(
    values: tuple[float, ...],
    mesh: AdaptiveMesh,
    iterations: int,
    strength: float,
) -> tuple[float, ...]:
    if iterations == 0 or strength == 0 or not mesh.triangles:
        return values
    boundary = _boundary_vertices(mesh.triangles)
    adjacency = _adjacency(len(values), mesh.triangles)
    current = list(values)
    for _ in range(iterations):
        next_values = list(current)
        for index, neighbors in enumerate(adjacency):
            if index in boundary or not neighbors:
                continue
            average = sum(current[neighbor] for neighbor in neighbors) / len(neighbors)
            next_values[index] = current[index] * (1 - strength) + average * strength
        current = next_values
    return tuple(current)


def compile_proxy_z_head(
    value: NormalizedRigInput,
    face_mesh: AdaptiveMesh,
    semantic_rig: SemanticRigPlanV1 | None = None,
    config: ProxyZConfig | None = None,
) -> ProxyZHeadPlanV1:
    config = config or ProxyZConfig()
    config.validate()
    if not face_mesh.positions:
        raise ValueError("face mesh must contain vertices")
    if any(
        max(triangle.a, triangle.b, triangle.c) >= len(face_mesh.positions)
        or min(triangle.a, triangle.b, triangle.c) < 0
        for triangle in face_mesh.triangles
    ):
        raise ValueError("face mesh triangle index out of range")

    face = _face_layer(value)
    rig = semantic_rig or compile_semantic_rig(value)
    if rig.character_id != value.character_id:
        raise ValueError("semantic rig character_id does not match input")
    head = _head_rule(rig)
    table = _landmarks(value)
    center = _profile_center(face, table, config.min_landmark_confidence)
    radius = _estimate_radius(face, table, config.min_landmark_confidence)

    findings: list[QaFinding] = []
    raw = [
        _base_depth(point, center, radius, config.radial_exponent)
        for point in face_mesh.positions
    ]
    features: list[DepthFeatureRule] = []
    nose_found = False
    for feature_id, aliases, strength, sigma_x, sigma_y in _FEATURE_SPECS:
        landmark = _find_landmark(table, aliases, config.min_landmark_confidence)
        if landmark is None:
            continue
        if feature_id == "nose":
            nose_found = True
        features.append(
            DepthFeatureRule(feature_id, landmark.id, strength, sigma_x, sigma_y)
        )
        for index, point in enumerate(face_mesh.positions):
            raw[index] += _gaussian_bias(
                point, landmark, radius, strength, sigma_x, sigma_y
            )

    if not nose_found:
        findings.append(
            QaFinding(
                "warning",
                "proxy-z-nose-fallback",
                "nose landmark missing; base ellipsoid used for central depth",
                face.id,
            )
        )

    clipped = tuple(max(-0.25, min(1.25, depth)) for depth in raw)
    smoothed = _smooth(
        clipped,
        face_mesh,
        config.smoothing_iterations,
        config.smoothing_strength,
    )
    proxy_z = tuple(
        round(max(-0.25, min(1.25, depth)), 8) for depth in smoothed
    )
    depth_scale = min(radius) * config.depth_scale_ratio
    data = Pseudo3DHeadDataV1(
        (head.pivot.x, head.pivot.y),
        radius,
        depth_scale,
        config.perspective,
        config.yaw_gain,
        config.pitch_gain,
    )
    present = {layer.semantic for layer in value.layers}
    part_biases = tuple(rule for rule in _PART_DEPTH_BIASES if rule.semantic in present)
    findings.sort(key=lambda finding: (finding.severity, finding.code, finding.layer_id or ""))
    return ProxyZHeadPlanV1(
        1,
        value.character_id,
        head.target_part_id,
        center,
        proxy_z,
        data,
        tuple(features),
        part_biases,
        tuple(findings),
    )


def pack_proxy_z_buffer(plan: ProxyZHeadPlanV1) -> bytes:
    return struct.pack("<" + "f" * len(plan.proxy_z), *plan.proxy_z)


def project_proxy_z_reference(
    x: float,
    y: float,
    proxy_z: float,
    angle_x_deg: float,
    angle_y_deg: float,
    data: Pseudo3DHeadDataV1,
) -> tuple[float, float]:
    """Mirror the Phase-1 Runtime pseudo3D reference projection exactly."""
    x0 = x - data.pivot[0]
    y0 = y - data.pivot[1]
    z0 = proxy_z * data.depth_scale

    yaw = angle_x_deg * data.yaw_gain * math.pi / 180
    pitch = angle_y_deg * data.pitch_gain * math.pi / 180
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    x1 = cy * x0 + sy * z0
    z1 = -sy * x0 + cy * z0
    y1 = cp * y0 - sp * z1
    z2 = sp * y0 + cp * z1

    depth_delta = z2 - z0
    perspective_scale = 1 / max(0.25, 1 + data.perspective * depth_delta)
    return (
        x1 * perspective_scale + data.pivot[0],
        y1 * perspective_scale + data.pivot[1],
    )
