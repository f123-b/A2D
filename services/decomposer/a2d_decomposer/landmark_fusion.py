from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Protocol

from .contract import (
    DecomposerFindingV1,
    DecomposerResultV1,
    NormalizedLandmarkV1,
    NormalizedLayerAssetV1,
    NormalizedLayerRecordV1,
    SourceImageRgba,
)
from .pipeline import canonicalize_landmark_label


@dataclass(frozen=True, slots=True)
class LandmarkCandidateV1:
    id: str
    x: float
    y: float
    confidence: float

    def validate(self) -> None:
        if not self.id:
            raise ValueError("landmark candidate id is required")
        if not all(math.isfinite(v) for v in (self.x, self.y, self.confidence)):
            raise ValueError(f"landmark candidate {self.id} must be finite")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError(f"landmark candidate {self.id} coordinates must be normalized")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"landmark candidate {self.id} confidence must be in [0,1]")


class LandmarkProvider(Protocol):
    provider_name: str
    provider_revision: str

    def infer_landmarks(
        self,
        image: SourceImageRgba,
        result: DecomposerResultV1,
    ) -> tuple[LandmarkCandidateV1, ...]: ...


class ScriptedReferenceLandmarkProvider:
    provider_name = "a2d-scripted-landmarks"
    provider_revision = "1"

    def __init__(self, candidates: tuple[LandmarkCandidateV1, ...]) -> None:
        self._candidates = candidates

    def infer_landmarks(
        self,
        image: SourceImageRgba,
        result: DecomposerResultV1,
    ) -> tuple[LandmarkCandidateV1, ...]:
        image.validate()
        return self._candidates


@dataclass(frozen=True, slots=True)
class LandmarkFusionConfig:
    preserve_confidence_threshold: float = 0.90
    low_confidence_threshold: float = 0.65
    disagreement_face_fraction: float = 0.18
    existing_weight: float = 1.00
    provider_weight: float = 1.10
    geometry_weight: float = 0.65
    disagreement_confidence_scale: float = 0.85
    hair_root_band_fraction: float = 0.18

    def validate(self) -> None:
        for name, value in (
            ("preserve_confidence_threshold", self.preserve_confidence_threshold),
            ("low_confidence_threshold", self.low_confidence_threshold),
            ("disagreement_face_fraction", self.disagreement_face_fraction),
            ("disagreement_confidence_scale", self.disagreement_confidence_scale),
            ("hair_root_band_fraction", self.hair_root_band_fraction),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.preserve_confidence_threshold <= 1:
            raise ValueError("preserve_confidence_threshold must be in [0,1]")
        if not 0 <= self.low_confidence_threshold <= 1:
            raise ValueError("low_confidence_threshold must be in [0,1]")
        if not 0 < self.disagreement_face_fraction <= 1:
            raise ValueError("disagreement_face_fraction must be in (0,1]")
        if not 0 < self.disagreement_confidence_scale <= 1:
            raise ValueError("disagreement_confidence_scale must be in (0,1]")
        if not 0 < self.hair_root_band_fraction <= 0.5:
            raise ValueError("hair_root_band_fraction must be in (0,0.5]")
        for name, value in (
            ("existing_weight", self.existing_weight),
            ("provider_weight", self.provider_weight),
            ("geometry_weight", self.geometry_weight),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class _Evidence:
    landmark: LandmarkCandidateV1
    source: str
    reliability: float


_CENTROID_RULES: tuple[tuple[str, str, float], ...] = (
    ("head_center", "face", 0.82),
    ("eye_l_center", "eye_white_l", 0.86),
    ("eye_r_center", "eye_white_r", 0.86),
    ("iris_l_center", "iris_l", 0.90),
    ("iris_r_center", "iris_r", 0.90),
    ("mouth_center", "mouth", 0.86),
    ("brow_l_center", "brow_l", 0.82),
    ("brow_r_center", "brow_r", 0.82),
)

_HAIR_ROOT_RULES: tuple[tuple[str, str], ...] = (
    ("hair_front_root", "hair_front"),
    ("hair_side_l_root", "hair_side_l"),
    ("hair_side_r_root", "hair_side_r"),
    ("hair_back_root", "hair_back"),
)


def _provider_identity(provider: LandmarkProvider) -> tuple[str, str]:
    name = getattr(provider, "provider_name", "")
    revision = getattr(provider, "provider_revision", "")
    if not isinstance(name, str) or not name:
        raise ValueError("landmark provider_name is required")
    if not isinstance(revision, str) or not revision:
        raise ValueError("landmark provider_revision is required")
    return name, revision


def _asset_tables(
    result: DecomposerResultV1,
) -> tuple[dict[str, NormalizedLayerRecordV1], dict[str, NormalizedLayerAssetV1]]:
    assets_by_id = {item.layer_id: item for item in result.assets}
    records = {
        item.semantic: item
        for item in result.layers
        if item.semantic != "accessory"
    }
    assets = {
        semantic: assets_by_id[record.id]
        for semantic, record in records.items()
        if record.id in assets_by_id
    }
    return records, assets


def _alpha_centroid(
    record: NormalizedLayerRecordV1,
    asset: NormalizedLayerAssetV1,
) -> tuple[float, float]:
    bx, by, bw, bh = record.bbox
    total = 0.0
    sx = 0.0
    sy = 0.0
    for y in range(asset.height):
        for x in range(asset.width):
            weight = float(asset.alpha[y * asset.width + x])
            if weight <= 0:
                continue
            total += weight
            sx += ((x + 0.5) / asset.width) * weight
            sy += ((y + 0.5) / asset.height) * weight
    if total <= 0:
        return (bx + bw * 0.5, by + bh * 0.5)
    return (bx + bw * (sx / total), by + bh * (sy / total))


def _top_band_centroid(
    record: NormalizedLayerRecordV1,
    asset: NormalizedLayerAssetV1,
    band_fraction: float,
) -> tuple[float, float]:
    active_rows = [
        y
        for y in range(asset.height)
        if any(asset.alpha[y * asset.width + x] > 0 for x in range(asset.width))
    ]
    if not active_rows:
        return _alpha_centroid(record, asset)
    min_y = min(active_rows)
    band_rows = max(1, int(math.ceil(asset.height * band_fraction)))
    max_y = min(asset.height - 1, min_y + band_rows - 1)
    bx, by, bw, bh = record.bbox
    total = 0.0
    sx = 0.0
    sy = 0.0
    for y in range(min_y, max_y + 1):
        for x in range(asset.width):
            weight = float(asset.alpha[y * asset.width + x])
            if weight <= 0:
                continue
            total += weight
            sx += ((x + 0.5) / asset.width) * weight
            sy += ((y + 0.5) / asset.height) * weight
    if total <= 0:
        return _alpha_centroid(record, asset)
    return (bx + bw * (sx / total), by + bh * (sy / total))


def _geometry_candidates(
    result: DecomposerResultV1,
    config: LandmarkFusionConfig,
) -> dict[str, LandmarkCandidateV1]:
    records, assets = _asset_tables(result)
    out: dict[str, LandmarkCandidateV1] = {}

    for landmark_id, semantic, scale in _CENTROID_RULES:
        record = records.get(semantic)
        asset = assets.get(semantic)
        if record is None or asset is None:
            continue
        x, y = _alpha_centroid(record, asset)
        out[landmark_id] = LandmarkCandidateV1(
            landmark_id, x, y, min(1.0, record.confidence * scale)
        )

    face = records.get("face")
    face_asset = assets.get("face")
    if face is not None and face_asset is not None:
        face_x, _ = _alpha_centroid(face, face_asset)
        fx, fy, fw, fh = face.bbox
        out["nose"] = LandmarkCandidateV1(
            "nose",
            face_x,
            min(1.0, max(0.0, fy + fh * 0.52)),
            min(1.0, face.confidence * 0.52),
        )

    body = records.get("body")
    body_asset = assets.get("body")
    if (
        face is not None
        and face_asset is not None
        and body is not None
        and body_asset is not None
    ):
        face_x, _ = _alpha_centroid(face, face_asset)
        body_x, _ = _alpha_centroid(body, body_asset)
        fx, fy, fw, fh = face.bbox
        bx, by, bw, bh = body.bbox
        y = (fy + fh + by) * 0.5
        y = min(1.0, max(0.0, y))
        out["neck"] = LandmarkCandidateV1(
            "neck",
            min(1.0, max(0.0, face_x * 0.75 + body_x * 0.25)),
            y,
            min(1.0, min(face.confidence, body.confidence) * 0.62),
        )

    for landmark_id, semantic in _HAIR_ROOT_RULES:
        record = records.get(semantic)
        asset = assets.get(semantic)
        if record is None or asset is None:
            continue
        x, y = _top_band_centroid(
            record, asset, config.hair_root_band_fraction
        )
        out[landmark_id] = LandmarkCandidateV1(
            landmark_id,
            x,
            y,
            min(1.0, record.confidence * 0.74),
        )

    return out


def _canonical_provider_candidates(
    provider: LandmarkProvider,
    image: SourceImageRgba,
    result: DecomposerResultV1,
) -> tuple[dict[str, LandmarkCandidateV1], list[DecomposerFindingV1]]:
    findings: list[DecomposerFindingV1] = []
    candidates: dict[str, LandmarkCandidateV1] = {}
    raw = provider.infer_landmarks(image, result)
    if not isinstance(raw, tuple):
        raise TypeError("landmark provider must return tuple[LandmarkCandidateV1, ...]")
    for item in sorted(raw, key=lambda value: (value.id, value.x, value.y)):
        if not isinstance(item, LandmarkCandidateV1):
            raise TypeError("landmark provider returned an invalid candidate")
        item.validate()
        canonical = canonicalize_landmark_label(item.id)
        if canonical is None:
            findings.append(DecomposerFindingV1(
                "info",
                "landmark-provider-unsupported",
                f"provider landmark {item.id} is not part of the A2D landmark vocabulary",
                item.id,
            ))
            continue
        if canonical in candidates:
            raise ValueError(f"duplicate provider landmark: {canonical}")
        candidates[canonical] = LandmarkCandidateV1(
            canonical, item.x, item.y, item.confidence
        )
    return candidates, findings


def _face_scale(result: DecomposerResultV1) -> float:
    face = next((item for item in result.layers if item.semantic == "face"), None)
    if face is None:
        return 1.0
    _, _, width, height = face.bbox
    return max(math.hypot(width, height), 1e-6)


def _distance(a: LandmarkCandidateV1, b: LandmarkCandidateV1) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _fuse_one(
    landmark_id: str,
    evidence: list[_Evidence],
    threshold: float,
    config: LandmarkFusionConfig,
    findings: list[DecomposerFindingV1],
) -> NormalizedLandmarkV1:
    existing = next((item for item in evidence if item.source == "existing"), None)
    if (
        existing is not None
        and existing.landmark.confidence >= config.preserve_confidence_threshold
    ):
        for other in evidence:
            if other is existing:
                continue
            if _distance(existing.landmark, other.landmark) > threshold:
                findings.append(DecomposerFindingV1(
                    "warning",
                    "landmark-disagreement",
                    f"{landmark_id} high-confidence existing landmark disagrees with {other.source}",
                    landmark_id,
                ))
                break
        return NormalizedLandmarkV1(
            landmark_id,
            existing.landmark.x,
            existing.landmark.y,
            existing.landmark.confidence,
        )

    disagreement = False
    for index, left in enumerate(evidence):
        for right in evidence[index + 1:]:
            if _distance(left.landmark, right.landmark) > threshold:
                disagreement = True
                break
        if disagreement:
            break

    if disagreement:
        strongest = max(
            evidence,
            key=lambda item: (
                item.landmark.confidence * item.reliability,
                item.source,
            ),
        )
        confidence = strongest.landmark.confidence * config.disagreement_confidence_scale
        findings.append(DecomposerFindingV1(
            "warning",
            "landmark-disagreement",
            f"{landmark_id} candidates disagree; selected {strongest.source}",
            landmark_id,
        ))
        return NormalizedLandmarkV1(
            landmark_id,
            strongest.landmark.x,
            strongest.landmark.y,
            min(1.0, confidence),
        )

    weights = [
        max(1e-9, item.landmark.confidence * item.reliability)
        for item in evidence
    ]
    total = sum(weights)
    x = sum(item.landmark.x * weight for item, weight in zip(evidence, weights)) / total
    y = sum(item.landmark.y * weight for item, weight in zip(evidence, weights)) / total
    confidence = sum(
        item.landmark.confidence * weight
        for item, weight in zip(evidence, weights)
    ) / total
    if len(evidence) > 1:
        confidence = min(1.0, confidence + 0.03)
        findings.append(DecomposerFindingV1(
            "info",
            "landmark-fused",
            f"{landmark_id} fused {len(evidence)} independent candidates",
            landmark_id,
        ))
    elif evidence[0].source == "geometry":
        findings.append(DecomposerFindingV1(
            "info",
            "landmark-geometry-inferred",
            f"{landmark_id} was inferred from normalized layer geometry",
            landmark_id,
        ))
    return NormalizedLandmarkV1(
        landmark_id,
        min(1.0, max(0.0, x)),
        min(1.0, max(0.0, y)),
        min(1.0, max(0.0, confidence)),
    )


def _revision(
    previous: str,
    config: LandmarkFusionConfig,
    provider_name: str,
    provider_revision: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(previous.encode("utf-8"))
    digest.update(repr(config).encode("utf-8"))
    digest.update(provider_name.encode("utf-8"))
    digest.update(provider_revision.encode("utf-8"))
    digest.update(b"p3-r5-landmark-fusion-v1")
    return f"sha256:{digest.hexdigest()}"


def fuse_landmarks(
    result: DecomposerResultV1,
    source_image: SourceImageRgba,
    provider: LandmarkProvider | None = None,
    *,
    config: LandmarkFusionConfig | None = None,
) -> DecomposerResultV1:
    """Fuse direct, provider, and geometry landmark evidence deterministically."""
    config = config or LandmarkFusionConfig()
    config.validate()
    source_image.validate()
    if source_image.width != result.canvas_width or source_image.height != result.canvas_height:
        raise ValueError("source image dimensions do not match decomposer result")

    findings = [
        item
        for item in result.findings
        if item.code != "landmark-low-confidence"
    ]
    existing: dict[str, LandmarkCandidateV1] = {}
    for item in result.landmarks:
        candidate = LandmarkCandidateV1(item.id, item.x, item.y, item.confidence)
        candidate.validate()
        if item.id in existing:
            raise ValueError(f"duplicate existing landmark: {item.id}")
        existing[item.id] = candidate

    provider_name = "none"
    provider_revision = "none"
    provider_candidates: dict[str, LandmarkCandidateV1] = {}
    if provider is not None:
        try:
            provider_name, provider_revision = _provider_identity(provider)
            provider_candidates, provider_findings = _canonical_provider_candidates(
                provider, source_image, result
            )
            findings.extend(provider_findings)
        except Exception as exc:
            findings.append(DecomposerFindingV1(
                "error",
                "landmark-provider-error",
                f"landmark provider failed: {type(exc).__name__}: {exc}",
                None,
            ))

    geometry = _geometry_candidates(result, config)
    all_ids = sorted(set(existing) | set(provider_candidates) | set(geometry))
    threshold = _face_scale(result) * config.disagreement_face_fraction
    fused: list[NormalizedLandmarkV1] = []

    for landmark_id in all_ids:
        evidence: list[_Evidence] = []
        if landmark_id in existing:
            evidence.append(_Evidence(
                existing[landmark_id], "existing", config.existing_weight
            ))
        if landmark_id in provider_candidates:
            evidence.append(_Evidence(
                provider_candidates[landmark_id], "provider", config.provider_weight
            ))
        if landmark_id in geometry:
            evidence.append(_Evidence(
                geometry[landmark_id], "geometry", config.geometry_weight
            ))
        if not evidence:
            continue
        item = _fuse_one(
            landmark_id, evidence, threshold, config, findings
        )
        fused.append(item)
        if item.confidence < config.low_confidence_threshold:
            findings.append(DecomposerFindingV1(
                "warning",
                "landmark-low-confidence",
                f"{landmark_id} fused confidence {item.confidence:.3f} is below "
                f"{config.low_confidence_threshold:.3f}",
                landmark_id,
            ))

    fused.sort(key=lambda item: item.id)
    findings.sort(key=lambda item: (
        {"error": 0, "warning": 1, "info": 2}.get(item.severity, 3),
        item.code,
        item.subject_id or "",
        item.message,
    ))
    return DecomposerResultV1(
        result.version,
        result.character_id,
        _revision(result.source_revision, config, provider_name, provider_revision),
        result.canvas_width,
        result.canvas_height,
        result.layers,
        tuple(fused),
        result.assets,
        tuple(findings),
    )
