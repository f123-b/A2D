from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


CANONICAL_SEMANTICS: tuple[str, ...] = (
    "body", "cloth", "face", "brow_l", "brow_r",
    "eye_white_l", "eye_white_r", "iris_l", "iris_r", "mouth",
    "hair_front", "hair_side_l", "hair_side_r", "hair_back", "accessory",
)


@dataclass(frozen=True, slots=True)
class SourceImageRgba:
    width: int
    height: int
    pixels: bytes

    def validate(self) -> None:
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise ValueError("source image width/height must be integers")
        if self.width < 1 or self.height < 1:
            raise ValueError("source image width/height must be positive")
        expected = self.width * self.height * 4
        if len(self.pixels) != expected:
            raise ValueError(f"source RGBA length {len(self.pixels)} does not equal {expected}")


@dataclass(frozen=True, slots=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    def validate(self, canvas_width: int, canvas_height: int) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(isinstance(value, int) for value in values):
            raise ValueError("pixel bbox values must be integers")
        if self.width < 1 or self.height < 1:
            raise ValueError("pixel bbox width/height must be positive")
        if self.x < 0 or self.y < 0:
            raise ValueError("pixel bbox origin must be non-negative")
        if self.x + self.width > canvas_width or self.y + self.height > canvas_height:
            raise ValueError("pixel bbox must remain inside source canvas")


@dataclass(frozen=True, slots=True)
class BackendLayerObservationV1:
    source_key: str
    semantic_label: str
    bbox: PixelRect
    rgba: bytes
    alpha: bytes
    z_order: int
    confidence: float = 1.0
    parent_source_key: str | None = None

    def validate(self, canvas_width: int, canvas_height: int) -> None:
        if not self.source_key:
            raise ValueError("backend layer source_key is required")
        if not self.semantic_label:
            raise ValueError(f"backend layer {self.source_key}: semantic_label is required")
        self.bbox.validate(canvas_width, canvas_height)
        pixel_count = self.bbox.width * self.bbox.height
        if len(self.rgba) != pixel_count * 4:
            raise ValueError(f"backend layer {self.source_key}: RGBA length does not match bbox")
        if len(self.alpha) != pixel_count:
            raise ValueError(f"backend layer {self.source_key}: alpha length does not match bbox")
        if not isinstance(self.z_order, int):
            raise ValueError(f"backend layer {self.source_key}: z_order must be an integer")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"backend layer {self.source_key}: confidence must be 0..1")
        if self.parent_source_key == self.source_key:
            raise ValueError(f"backend layer {self.source_key}: cannot parent itself")


@dataclass(frozen=True, slots=True)
class BackendLandmarkObservationV1:
    label: str
    x: float
    y: float
    confidence: float = 1.0

    def validate(self, canvas_width: int, canvas_height: int) -> None:
        if not self.label:
            raise ValueError("backend landmark label is required")
        if not 0 <= self.x <= canvas_width or not 0 <= self.y <= canvas_height:
            raise ValueError(f"backend landmark {self.label}: coordinates must remain inside source canvas")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"backend landmark {self.label}: confidence must be 0..1")


@dataclass(frozen=True, slots=True)
class BackendDecompositionV1:
    layers: tuple[BackendLayerObservationV1, ...]
    landmarks: tuple[BackendLandmarkObservationV1, ...] = ()
    backend_name: str = "unknown"
    backend_revision: str | None = None


class DecompositionBackend(Protocol):
    def decompose(self, image: SourceImageRgba) -> BackendDecompositionV1: ...


@dataclass(frozen=True, slots=True, order=True)
class DecomposerFindingV1:
    severity: str
    code: str
    message: str
    subject_id: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedLayerAssetV1:
    layer_id: str
    semantic: str
    width: int
    height: int
    rgba: bytes
    alpha: bytes


@dataclass(frozen=True, slots=True)
class NormalizedLayerRecordV1:
    id: str
    semantic: str
    image_uri: str
    mask_uri: str
    bbox: tuple[float, float, float, float]
    z_order: int
    confidence: float
    parent_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        x, y, width, height = self.bbox
        result: dict[str, object] = {
            "id": self.id,
            "semantic": self.semantic,
            "imageUri": self.image_uri,
            "maskUri": self.mask_uri,
            "bbox": {"x": x, "y": y, "width": width, "height": height},
            "zOrder": self.z_order,
            "confidence": self.confidence,
        }
        if self.parent_id is not None:
            result["parentId"] = self.parent_id
        return result


@dataclass(frozen=True, slots=True)
class NormalizedLandmarkV1:
    id: str
    x: float
    y: float
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "x": self.x, "y": self.y, "confidence": self.confidence}


@dataclass(frozen=True, slots=True)
class DecomposerResultV1:
    version: int
    character_id: str
    source_revision: str
    canvas_width: int
    canvas_height: int
    layers: tuple[NormalizedLayerRecordV1, ...]
    landmarks: tuple[NormalizedLandmarkV1, ...]
    assets: tuple[NormalizedLayerAssetV1, ...]
    findings: tuple[DecomposerFindingV1, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)

    def package_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "characterId": self.character_id,
            "sourceRevision": self.source_revision,
            "canvas": {"width": self.canvas_width, "height": self.canvas_height},
            "layers": [item.to_dict() for item in self.layers],
            "landmarks": [item.to_dict() for item in self.landmarks],
        }

    def asset_bytes(self) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        records = {item.id: item for item in self.layers}
        for asset in self.assets:
            record = records[asset.layer_id]
            out[record.image_uri] = asset.rgba
            out[record.mask_uri] = asset.alpha
        return out
