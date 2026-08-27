from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .contract import (
    BackendDecompositionV1,
    BackendLandmarkObservationV1,
    BackendLayerObservationV1,
    CANONICAL_SEMANTICS,
    DecomposerFindingV1,
    DecomposerResultV1,
    DecompositionBackend,
    NormalizedLandmarkV1,
    NormalizedLayerAssetV1,
    NormalizedLayerRecordV1,
    PixelRect,
    SourceImageRgba,
)


_SEMANTIC_ALIASES: dict[str, str] = {
    **{value: value for value in CANONICAL_SEMANTICS},
    "torso": "body", "base_body": "body",
    "clothes": "cloth", "clothing": "cloth", "outfit": "cloth",
    "head_skin": "face", "facial_skin": "face",
    "left_brow": "brow_l", "eyebrow_left": "brow_l",
    "right_brow": "brow_r", "eyebrow_right": "brow_r",
    "eye_l": "eye_white_l", "left_eye": "eye_white_l", "sclera_left": "eye_white_l",
    "eye_r": "eye_white_r", "right_eye": "eye_white_r", "sclera_right": "eye_white_r",
    "iris_left": "iris_l", "left_iris": "iris_l",
    "iris_right": "iris_r", "right_iris": "iris_r",
    "lips": "mouth", "oral": "mouth",
    "bangs": "hair_front", "front_hair": "hair_front",
    "hair_left": "hair_side_l", "left_hair": "hair_side_l",
    "hair_right": "hair_side_r", "right_hair": "hair_side_r",
    "rear_hair": "hair_back", "back_hair": "hair_back",
    "ornament": "accessory", "prop": "accessory",
}

_LANDMARK_ALIASES: dict[str, str] = {
    "face_center": "face_center", "head_center": "head_center", "nose": "nose",
    "neck": "neck", "neck_center": "neck_center",
    "left_eye_center": "eye_l_center", "eye_left_center": "eye_l_center", "eye_l_center": "eye_l_center",
    "right_eye_center": "eye_r_center", "eye_right_center": "eye_r_center", "eye_r_center": "eye_r_center",
    "left_iris_center": "iris_l_center", "iris_left_center": "iris_l_center", "iris_l_center": "iris_l_center",
    "right_iris_center": "iris_r_center", "iris_right_center": "iris_r_center", "iris_r_center": "iris_r_center",
    "mouth_center": "mouth_center",
    "left_brow_center": "brow_l_center", "brow_l_center": "brow_l_center",
    "right_brow_center": "brow_r_center", "brow_r_center": "brow_r_center",
    "hair_front_root": "hair_front_root", "hair_side_l_root": "hair_side_l_root",
    "hair_side_r_root": "hair_side_r_root", "hair_back_root": "hair_back_root",
}


@dataclass(frozen=True, slots=True)
class DecomposerConfig:
    alpha_threshold: int = 1
    low_confidence_threshold: float = 0.65

    def validate(self) -> None:
        if not isinstance(self.alpha_threshold, int) or not 1 <= self.alpha_threshold <= 255:
            raise ValueError("alpha_threshold must be an integer in 1..255")
        if not 0 <= self.low_confidence_threshold <= 1:
            raise ValueError("low_confidence_threshold must be 0..1")


class ScriptedReferenceBackend:
    """Deterministic backend used by tests and adapter development.

    Real AI backends implement the same DecompositionBackend protocol and return
    BackendDecompositionV1 observations; the normalization path remains unchanged.
    """

    def __init__(self, result: BackendDecompositionV1) -> None:
        self._result = result

    def decompose(self, image: SourceImageRgba) -> BackendDecompositionV1:
        image.validate()
        return self._result


def _token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized


def canonicalize_semantic_label(label: str) -> str | None:
    return _SEMANTIC_ALIASES.get(_token(label))


def canonicalize_landmark_label(label: str) -> str | None:
    return _LANDMARK_ALIASES.get(_token(label))


def _tight_rect(alpha: bytes, width: int, height: int, threshold: int) -> PixelRect | None:
    min_x, min_y = width, height
    max_x = max_y = -1
    for y in range(height):
        row = y * width
        for x in range(width):
            if alpha[row + x] >= threshold:
                min_x = min(min_x, x); min_y = min(min_y, y)
                max_x = max(max_x, x); max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return None
    return PixelRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def _crop_alpha(alpha: bytes, width: int, rect: PixelRect) -> bytes:
    out = bytearray(rect.width * rect.height)
    for y in range(rect.height):
        src = (rect.y + y) * width + rect.x
        dst = y * rect.width
        out[dst:dst + rect.width] = alpha[src:src + rect.width]
    return bytes(out)


def _crop_rgba_masked(rgba: bytes, alpha: bytes, width: int, rect: PixelRect) -> bytes:
    out = bytearray(rect.width * rect.height * 4)
    for y in range(rect.height):
        for x in range(rect.width):
            source_x, source_y = rect.x + x, rect.y + y
            source_pixel = source_y * width + source_x
            source_offset = source_pixel * 4
            dest_offset = (y * rect.width + x) * 4
            mask_alpha = alpha[source_pixel]
            src_alpha = rgba[source_offset + 3]
            out[dest_offset:dest_offset + 3] = rgba[source_offset:source_offset + 3]
            out[dest_offset + 3] = (src_alpha * mask_alpha + 127) // 255
    return bytes(out)


def _normalized_bbox(canvas_width: int, canvas_height: int, rect: PixelRect) -> tuple[float, float, float, float]:
    return (
        rect.x / canvas_width,
        rect.y / canvas_height,
        rect.width / canvas_width,
        rect.height / canvas_height,
    )


def _source_revision(image: SourceImageRgba, backend: BackendDecompositionV1) -> str:
    digest = hashlib.sha256()
    digest.update(image.width.to_bytes(4, "little"))
    digest.update(image.height.to_bytes(4, "little"))
    digest.update(image.pixels)
    digest.update(backend.backend_name.encode("utf-8"))
    digest.update((backend.backend_revision or "").encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def _stable_ids(candidates: list[tuple[str, BackendLayerObservationV1]]) -> dict[str, str]:
    by_semantic: dict[str, list[BackendLayerObservationV1]] = {}
    for semantic, item in candidates:
        by_semantic.setdefault(semantic, []).append(item)
    result: dict[str, str] = {}
    for semantic, items in sorted(by_semantic.items()):
        ordered = sorted(items, key=lambda item: (item.z_order, item.source_key))
        if semantic != "accessory" and len(ordered) > 1:
            keys = ", ".join(item.source_key for item in ordered)
            raise ValueError(f"duplicate canonical semantic {semantic}: {keys}")
        if semantic == "accessory":
            for index, item in enumerate(ordered, 1):
                result[item.source_key] = f"accessory-{index:03d}"
        else:
            result[ordered[0].source_key] = semantic.replace("_", "-")
    return result


def _validate_parent_graph(stable_ids: dict[str, str], candidates: list[tuple[str, BackendLayerObservationV1]]) -> None:
    parent_by_key = {
        item.source_key: item.parent_source_key
        for _, item in candidates
        if item.parent_source_key is not None
    }
    retained = set(stable_ids)
    for child, parent in parent_by_key.items():
        if parent not in retained:
            raise ValueError(f"layer {child}: parent_source_key does not resolve to retained layer")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            raise ValueError(f"backend layer parent graph contains a cycle at {key}")
        visiting.add(key)
        parent = parent_by_key.get(key)
        if parent is not None:
            visit(parent)
        visiting.remove(key)
        visited.add(key)
    for key in sorted(retained):
        visit(key)


def _normalize_landmarks(
    observations: tuple[BackendLandmarkObservationV1, ...],
    image: SourceImageRgba,
    config: DecomposerConfig,
    findings: list[DecomposerFindingV1],
) -> tuple[NormalizedLandmarkV1, ...]:
    normalized: dict[str, NormalizedLandmarkV1] = {}
    for item in sorted(observations, key=lambda value: (_token(value.label), value.x, value.y)):
        item.validate(image.width, image.height)
        canonical = canonicalize_landmark_label(item.label)
        if canonical is None:
            findings.append(DecomposerFindingV1("info", "landmark-unsupported", f"unsupported landmark label: {item.label}", item.label))
            continue
        if canonical in normalized:
            raise ValueError(f"duplicate canonical landmark: {canonical}")
        landmark = NormalizedLandmarkV1(
            canonical,
            item.x / image.width,
            item.y / image.height,
            item.confidence,
        )
        normalized[canonical] = landmark
        if item.confidence < config.low_confidence_threshold:
            findings.append(DecomposerFindingV1("warning", "landmark-low-confidence", f"{canonical} confidence {item.confidence:.3f} is below {config.low_confidence_threshold:.3f}", canonical))
    return tuple(normalized[key] for key in sorted(normalized))


def normalize_backend_output(
    character_id: str,
    image: SourceImageRgba,
    backend_output: BackendDecompositionV1,
    *,
    config: DecomposerConfig | None = None,
) -> DecomposerResultV1:
    config = config or DecomposerConfig()
    config.validate()
    image.validate()
    if not character_id:
        raise ValueError("character_id is required")

    findings: list[DecomposerFindingV1] = []
    retained: list[tuple[str, BackendLayerObservationV1]] = []
    source_keys: set[str] = set()
    for item in sorted(backend_output.layers, key=lambda value: value.source_key):
        item.validate(image.width, image.height)
        if item.source_key in source_keys:
            raise ValueError(f"duplicate backend source_key: {item.source_key}")
        source_keys.add(item.source_key)
        semantic = canonicalize_semantic_label(item.semantic_label)
        if semantic is None:
            findings.append(DecomposerFindingV1("info", "semantic-unsupported", f"unsupported semantic label: {item.semantic_label}", item.source_key))
            continue
        retained.append((semantic, item))

    stable_ids = _stable_ids(retained)
    _validate_parent_graph(stable_ids, retained)
    layers: list[NormalizedLayerRecordV1] = []
    assets: list[NormalizedLayerAssetV1] = []
    for semantic, item in sorted(retained, key=lambda pair: (pair[1].z_order, pair[0], pair[1].source_key)):
        tight = _tight_rect(item.alpha, item.bbox.width, item.bbox.height, config.alpha_threshold)
        if tight is None:
            findings.append(DecomposerFindingV1("error", "layer-empty-mask", f"{item.source_key} alpha mask has no active pixels", item.source_key))
            continue
        full_rect = PixelRect(item.bbox.x + tight.x, item.bbox.y + tight.y, tight.width, tight.height)
        layer_id = stable_ids[item.source_key]
        image_uri = f"layers/{layer_id}.rgba"
        mask_uri = f"masks/{layer_id}.a8"
        parent_id = stable_ids.get(item.parent_source_key) if item.parent_source_key is not None else None
        record = NormalizedLayerRecordV1(
            layer_id,
            semantic,
            image_uri,
            mask_uri,
            _normalized_bbox(image.width, image.height, full_rect),
            item.z_order,
            item.confidence,
            parent_id,
        )
        cropped_alpha = _crop_alpha(item.alpha, item.bbox.width, tight)
        cropped_rgba = _crop_rgba_masked(item.rgba, item.alpha, item.bbox.width, tight)
        layers.append(record)
        assets.append(NormalizedLayerAssetV1(layer_id, semantic, tight.width, tight.height, cropped_rgba, cropped_alpha))
        if item.confidence < config.low_confidence_threshold:
            findings.append(DecomposerFindingV1("warning", "layer-low-confidence", f"{semantic} confidence {item.confidence:.3f} is below {config.low_confidence_threshold:.3f}", layer_id))

    landmarks = _normalize_landmarks(backend_output.landmarks, image, config, findings)
    findings.sort(key=lambda item: ({"error": 0, "warning": 1, "info": 2}.get(item.severity, 3), item.code, item.subject_id or "", item.message))
    layers.sort(key=lambda item: (item.z_order, item.id))
    assets.sort(key=lambda item: item.layer_id)
    return DecomposerResultV1(
        1,
        character_id,
        _source_revision(image, backend_output),
        image.width,
        image.height,
        tuple(layers),
        landmarks,
        tuple(assets),
        tuple(findings),
    )


def decompose_image(
    character_id: str,
    image: SourceImageRgba,
    backend: DecompositionBackend,
    *,
    config: DecomposerConfig | None = None,
) -> DecomposerResultV1:
    image.validate()
    output = backend.decompose(image)
    if not isinstance(output, BackendDecompositionV1):
        raise TypeError("decomposition backend must return BackendDecompositionV1")
    return normalize_backend_output(character_id, image, output, config=config)
