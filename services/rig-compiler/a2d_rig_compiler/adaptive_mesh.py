from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct
from typing import Iterable

from .contract import Landmark, NormalizedRect, Semantic, SemanticLayer


_EPS = 1e-12


@dataclass(frozen=True, slots=True, order=True)
class Point2:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Triangle:
    a: int
    b: int
    c: int


@dataclass(frozen=True, slots=True)
class AlphaMask:
    width: int
    height: int
    alpha: tuple[float, ...]

    def validate(self) -> None:
        if self.width < 2 or self.height < 2:
            raise ValueError("alpha mask dimensions must be >= 2")
        if len(self.alpha) != self.width * self.height:
            raise ValueError("alpha mask length mismatch")
        if any(not math.isfinite(v) or v < 0 or v > 1 for v in self.alpha):
            raise ValueError("alpha values must be finite in [0,1]")

    def sample(self, u: float, v: float) -> float:
        """Bilinear sample in layer-local normalized coordinates."""
        u = min(1.0, max(0.0, u))
        v = min(1.0, max(0.0, v))
        x = u * (self.width - 1)
        y = v * (self.height - 1)
        x0 = int(math.floor(x)); y0 = int(math.floor(y))
        x1 = min(self.width - 1, x0 + 1); y1 = min(self.height - 1, y0 + 1)
        tx = x - x0; ty = y - y0
        def a(ix: int, iy: int) -> float:
            return self.alpha[iy * self.width + ix]
        top = a(x0, y0) * (1 - tx) + a(x1, y0) * tx
        bottom = a(x0, y1) * (1 - tx) + a(x1, y1) * tx
        return top * (1 - ty) + bottom * ty

    def active_fraction(self, threshold: float) -> float:
        active = sum(1 for value in self.alpha if value >= threshold)
        return active / len(self.alpha)

    @classmethod
    def from_u8(cls, width: int, height: int, alpha: bytes | bytearray | memoryview) -> "AlphaMask":
        if len(alpha) != width * height:
            raise ValueError("u8 alpha mask length mismatch")
        return cls(width, height, tuple(value / 255.0 for value in alpha))


@dataclass(frozen=True, slots=True)
class MeshConfig:
    alpha_threshold: float = 0.30
    target_spacing: float = 0.12
    max_vertices: int = 512
    max_boundary_points: int = 192
    min_triangle_area: float = 1e-8
    min_triangle_angle_degrees: float = 2.0
    min_angle_warning_degrees: float = 5.0
    coverage_warning_ratio: float = 0.70

    def validate(self) -> None:
        if not 0 <= self.alpha_threshold <= 1:
            raise ValueError("alpha_threshold must be 0..1")
        if not 0 < self.target_spacing <= 1:
            raise ValueError("target_spacing must be in (0,1]")
        if self.max_vertices < 8:
            raise ValueError("max_vertices must be >= 8")
        if self.max_boundary_points < 4:
            raise ValueError("max_boundary_points must be >= 4")


@dataclass(frozen=True, slots=True)
class MeshFinding:
    severity: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MeshQuality:
    vertex_count: int
    triangle_count: int
    min_angle_degrees: float
    max_edge: float
    coverage_ratio: float
    degenerate_triangles_removed: int
    findings: tuple[MeshFinding, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AdaptiveMesh:
    positions: tuple[Point2, ...]
    uvs: tuple[Point2, ...]
    triangles: tuple[Triangle, ...]
    quality: MeshQuality


@dataclass(frozen=True, slots=True)
class PackedMeshBuffers:
    positions: bytes
    uvs: bytes
    indices: bytes
    index_component_type: str


class MeshGenerationError(ValueError):
    pass


_SEMANTIC_VERTEX_BUDGET: dict[Semantic, int] = {
    Semantic.BODY: 320,
    Semantic.CLOTH: 256,
    Semantic.FACE: 512,
    Semantic.BROW_L: 160,
    Semantic.BROW_R: 160,
    Semantic.EYE_WHITE_L: 192,
    Semantic.EYE_WHITE_R: 192,
    Semantic.IRIS_L: 128,
    Semantic.IRIS_R: 128,
    Semantic.MOUTH: 192,
    Semantic.HAIR_FRONT: 384,
    Semantic.HAIR_SIDE_L: 320,
    Semantic.HAIR_SIDE_R: 320,
    Semantic.HAIR_BACK: 384,
    Semantic.ACCESSORY: 256,
}


def default_mesh_config(semantic: Semantic) -> MeshConfig:
    budget = _SEMANTIC_VERTEX_BUDGET.get(semantic, 256)
    return MeshConfig(
        max_vertices=budget,
        max_boundary_points=min(192, max(24, budget // 2)),
    )


_SEMANTIC_DENSITY: dict[Semantic, float] = {
    Semantic.BODY: 0.75,
    Semantic.CLOTH: 0.90,
    Semantic.FACE: 1.30,
    Semantic.BROW_L: 1.50,
    Semantic.BROW_R: 1.50,
    Semantic.EYE_WHITE_L: 1.80,
    Semantic.EYE_WHITE_R: 1.80,
    Semantic.IRIS_L: 1.80,
    Semantic.IRIS_R: 1.80,
    Semantic.MOUTH: 1.80,
    Semantic.HAIR_FRONT: 1.15,
    Semantic.HAIR_SIDE_L: 1.05,
    Semantic.HAIR_SIDE_R: 1.05,
    Semantic.HAIR_BACK: 0.95,
    Semantic.ACCESSORY: 1.00,
}


def _local_to_canvas(p: Point2, bbox: NormalizedRect) -> Point2:
    return Point2(bbox.x + p.x * bbox.width, bbox.y + p.y * bbox.height)


def _canvas_to_local(p: Point2, bbox: NormalizedRect) -> Point2:
    return Point2((p.x - bbox.x) / bbox.width, (p.y - bbox.y) / bbox.height)


def _boundary_points(mask: AlphaMask, threshold: float) -> list[Point2]:
    """Return exposed cell-edge endpoints in local [0,1] coordinates."""
    w, h = mask.width, mask.height
    active = [[mask.alpha[y*w+x] >= threshold for x in range(w)] for y in range(h)]
    points: set[Point2] = set()
    for y in range(h):
        for x in range(w):
            if not active[y][x]:
                continue
            x0, x1 = x / w, (x + 1) / w
            y0, y1 = y / h, (y + 1) / h
            if y == 0 or not active[y-1][x]:
                points.update((Point2(x0, y0), Point2(x1, y0)))
            if y == h-1 or not active[y+1][x]:
                points.update((Point2(x0, y1), Point2(x1, y1)))
            if x == 0 or not active[y][x-1]:
                points.update((Point2(x0, y0), Point2(x0, y1)))
            if x == w-1 or not active[y][x+1]:
                points.update((Point2(x1, y0), Point2(x1, y1)))
    return list(points)


def _farthest_reduce(points: Iterable[Point2], limit: int) -> list[Point2]:
    """Deterministic farthest-point sampling; preserves disconnected contours."""
    candidates = sorted(set(points))
    if len(candidates) <= limit:
        return candidates
    selected = [candidates[0]]
    remaining = candidates[1:]
    min_d2 = [((p.x-selected[0].x)**2 + (p.y-selected[0].y)**2) for p in remaining]
    while remaining and len(selected) < limit:
        best_i = max(range(len(remaining)), key=lambda i: (min_d2[i], -remaining[i].x, -remaining[i].y))
        chosen = remaining.pop(best_i)
        min_d2.pop(best_i)
        selected.append(chosen)
        for i, point in enumerate(remaining):
            d2 = (point.x-chosen.x)**2 + (point.y-chosen.y)**2
            if d2 < min_d2[i]:
                min_d2[i] = d2
    return sorted(selected)


def _feature_points(
    landmarks: Iterable[Landmark],
    bbox: NormalizedRect,
    mask: AlphaMask,
    threshold: float,
) -> list[Point2]:
    out: list[Point2] = []
    for lm in landmarks:
        if lm.confidence <= 0:
            continue
        if bbox.x <= lm.x <= bbox.x+bbox.width and bbox.y <= lm.y <= bbox.y+bbox.height:
            local = _canvas_to_local(Point2(lm.x, lm.y), bbox)
            if mask.sample(local.x, local.y) >= threshold:
                out.append(local)
    return sorted(set(out))


def _semantic_spacing(semantic: Semantic, config: MeshConfig) -> float:
    density = _SEMANTIC_DENSITY.get(semantic, 1.0)
    return max(0.025, min(0.35, config.target_spacing / density))


def _interior_points(mask: AlphaMask, semantic: Semantic, config: MeshConfig) -> list[Point2]:
    spacing = _semantic_spacing(semantic, config)
    out: list[Point2] = []
    y = spacing * 0.5
    while y < 1:
        x = spacing * 0.5
        while x < 1:
            if mask.sample(x, y) >= config.alpha_threshold:
                out.append(Point2(round(x, 10), round(y, 10)))
            x += spacing
        y += spacing
    return out


def _orient(a: Point2, b: Point2, c: Point2) -> float:
    return (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x)


def _circumcircle_contains(a: Point2, b: Point2, c: Point2, p: Point2) -> bool:
    ax, ay = a.x-p.x, a.y-p.y
    bx, by = b.x-p.x, b.y-p.y
    cx, cy = c.x-p.x, c.y-p.y
    det = (
        (ax*ax+ay*ay) * (bx*cy-cx*by)
        - (bx*bx+by*by) * (ax*cy-cx*ay)
        + (cx*cx+cy*cy) * (ax*by-bx*ay)
    )
    orientation = _orient(a, b, c)
    return det > _EPS if orientation > 0 else det < -_EPS


def _delaunay(points: list[Point2]) -> list[Triangle]:
    if len(points) < 3:
        return []
    pts = list(points)
    s0, s1, s2 = Point2(-8, -8), Point2(8, -8), Point2(0, 8)
    super_start = len(pts)
    pts.extend((s0, s1, s2))
    triangles = [Triangle(super_start, super_start+1, super_start+2)]

    for pi in range(super_start):
        p = pts[pi]
        bad: list[Triangle] = []
        edge_count: dict[tuple[int,int], int] = {}
        for tri in triangles:
            if _circumcircle_contains(pts[tri.a], pts[tri.b], pts[tri.c], p):
                bad.append(tri)
                for u, v in ((tri.a,tri.b),(tri.b,tri.c),(tri.c,tri.a)):
                    edge = (u,v) if u < v else (v,u)
                    edge_count[edge] = edge_count.get(edge, 0) + 1
        if not bad:
            continue
        bad_set = set(bad)
        triangles = [tri for tri in triangles if tri not in bad_set]
        boundary = sorted(edge for edge, count in edge_count.items() if count == 1)
        for u, v in boundary:
            tri = Triangle(u, v, pi)
            if _orient(pts[tri.a], pts[tri.b], pts[tri.c]) < 0:
                tri = Triangle(v, u, pi)
            triangles.append(tri)

    return [
        tri for tri in triangles
        if tri.a < super_start and tri.b < super_start and tri.c < super_start
    ]


def _triangle_area(a: Point2, b: Point2, c: Point2) -> float:
    return abs(_orient(a,b,c)) * 0.5


def _edge(a: Point2, b: Point2) -> float:
    return math.hypot(a.x-b.x, a.y-b.y)


def _triangle_min_angle(a: Point2, b: Point2, c: Point2) -> float:
    lengths = (_edge(b,c), _edge(a,c), _edge(a,b))
    angles: list[float] = []
    for opposite, l1, l2 in ((lengths[0], lengths[1], lengths[2]), (lengths[1], lengths[0], lengths[2]), (lengths[2], lengths[0], lengths[1])):
        denom = max(_EPS, 2*l1*l2)
        cosv = max(-1.0, min(1.0, (l1*l1+l2*l2-opposite*opposite)/denom))
        angles.append(math.degrees(math.acos(cosv)))
    return min(angles)


def _inside_triangle_samples(tri: Triangle, local_points: list[Point2], mask: AlphaMask, threshold: float) -> bool:
    a,b,c = (local_points[tri.a], local_points[tri.b], local_points[tri.c])
    samples = (
        Point2((a.x+b.x+c.x)/3, (a.y+b.y+c.y)/3),
        Point2((a.x+b.x)/2, (a.y+b.y)/2),
        Point2((b.x+c.x)/2, (b.y+c.y)/2),
        Point2((c.x+a.x)/2, (c.y+a.y)/2),
    )
    return mask.sample(samples[0].x, samples[0].y) >= threshold and all(
        mask.sample(p.x,p.y) >= threshold*0.5 for p in samples[1:]
    )


def generate_adaptive_mesh(
    semantic: Semantic,
    bbox: NormalizedRect,
    mask: AlphaMask,
    landmarks: Iterable[Landmark] = (),
    config: MeshConfig | None = None,
) -> AdaptiveMesh:
    config = config or default_mesh_config(semantic)
    bbox.validate()
    mask.validate()
    config.validate()
    if mask.active_fraction(config.alpha_threshold) == 0:
        raise MeshGenerationError("alpha mask contains no active pixels")

    spacing = _semantic_spacing(semantic, config)
    adaptive_boundary_limit = max(16, math.ceil(4.0 / spacing))
    boundary = _farthest_reduce(
        _boundary_points(mask, config.alpha_threshold),
        min(config.max_boundary_points, config.max_vertices, adaptive_boundary_limit),
    )
    features = _feature_points(landmarks, bbox, mask, config.alpha_threshold)
    interior = sorted(set(_interior_points(mask, semantic, config)))

    local: list[Point2] = []
    seen: set[Point2] = set()
    for seq in (features, boundary):
        for point in seq:
            if point not in seen and len(local) < config.max_vertices:
                seen.add(point); local.append(point)
    for point in interior:
        if point not in seen and len(local) < config.max_vertices:
            seen.add(point); local.append(point)

    local = sorted(local)
    if len(local) < 3:
        raise MeshGenerationError("not enough sampled points to triangulate")

    raw = _delaunay(local)
    retained: list[Triangle] = []
    degenerates = 0
    for tri in raw:
        a,b,c = local[tri.a], local[tri.b], local[tri.c]
        area = _triangle_area(a,b,c)
        if area < config.min_triangle_area:
            degenerates += 1
            continue
        if _triangle_min_angle(a, b, c) < config.min_triangle_angle_degrees:
            degenerates += 1
            continue
        if _inside_triangle_samples(tri, local, mask, config.alpha_threshold):
            retained.append(tri)
    if not retained:
        raise MeshGenerationError("triangulation produced no alpha-covered triangles")

    used = sorted({i for tri in retained for i in (tri.a, tri.b, tri.c)})
    remap = {old: new for new, old in enumerate(used)}
    compact_local = [local[i] for i in used]
    triangles = tuple(Triangle(remap[t.a], remap[t.b], remap[t.c]) for t in retained)
    positions = tuple(_local_to_canvas(p, bbox) for p in compact_local)
    uvs = tuple(compact_local)

    min_angle = 180.0
    max_edge = 0.0
    total_area = 0.0
    for tri in triangles:
        a,b,c = (compact_local[tri.a], compact_local[tri.b], compact_local[tri.c])
        min_angle = min(min_angle, _triangle_min_angle(a,b,c))
        max_edge = max(max_edge, _edge(a,b), _edge(b,c), _edge(c,a))
        total_area += _triangle_area(a,b,c)

    mask_area = mask.active_fraction(config.alpha_threshold)
    coverage = min(1.0, total_area / max(_EPS, mask_area))
    findings: list[MeshFinding] = []
    if min_angle < config.min_angle_warning_degrees:
        findings.append(MeshFinding("warning", "mesh-small-angle", f"minimum triangle angle {min_angle:.2f}°"))
    if coverage < config.coverage_warning_ratio:
        findings.append(MeshFinding("warning", "mesh-low-coverage", f"estimated alpha coverage {coverage:.3f}"))

    quality = MeshQuality(
        vertex_count=len(positions),
        triangle_count=len(triangles),
        min_angle_degrees=min_angle,
        max_edge=max_edge,
        coverage_ratio=coverage,
        degenerate_triangles_removed=degenerates,
        findings=tuple(findings),
    )
    return AdaptiveMesh(positions, uvs, triangles, quality)


def generate_layer_mesh(
    layer: SemanticLayer,
    mask: AlphaMask,
    landmarks: Iterable[Landmark] = (),
    config: MeshConfig | None = None,
) -> AdaptiveMesh:
    """Generate a canvas-normalized mesh for one P2-R1 semantic layer."""
    layer.validate()
    return generate_adaptive_mesh(layer.semantic, layer.bbox, mask, landmarks, config)


def assert_mesh_quality(
    mesh: AdaptiveMesh,
    *,
    min_coverage_ratio: float = 0.55,
    min_angle_degrees: float = 1.0,
) -> None:
    if mesh.quality.coverage_ratio < min_coverage_ratio:
        raise MeshGenerationError(
            f"mesh coverage {mesh.quality.coverage_ratio:.3f} < {min_coverage_ratio:.3f}"
        )
    if mesh.quality.min_angle_degrees < min_angle_degrees:
        raise MeshGenerationError(
            f"mesh min angle {mesh.quality.min_angle_degrees:.3f}° < {min_angle_degrees:.3f}°"
        )


def pack_mesh_buffers(mesh: AdaptiveMesh) -> PackedMeshBuffers:
    positions = b"".join(struct.pack("<ff", p.x, p.y) for p in mesh.positions)
    uvs = b"".join(struct.pack("<ff", p.x, p.y) for p in mesh.uvs)
    indices_flat = [v for tri in mesh.triangles for v in (tri.a,tri.b,tri.c)]
    if len(mesh.positions) <= 0xFFFF:
        indices = b"".join(struct.pack("<H", i) for i in indices_flat)
        component = "u16"
    else:
        indices = b"".join(struct.pack("<I", i) for i in indices_flat)
        component = "u32"
    return PackedMeshBuffers(positions, uvs, indices, component)
