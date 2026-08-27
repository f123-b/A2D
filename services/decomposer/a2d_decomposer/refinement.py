from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .contract import (
    DecomposerFindingV1,
    DecomposerResultV1,
    NormalizedLayerAssetV1,
    NormalizedLayerRecordV1,
    SourceImageRgba,
)


_PAIR_RULES: tuple[tuple[str, str], ...] = (
    ("eye_white_l", "eye_white_r"),
    ("iris_l", "iris_r"),
    ("brow_l", "brow_r"),
)

_REQUIRED: frozenset[str] = frozenset(
    {"body", "face", "eye_white_l", "eye_white_r", "iris_l", "iris_r", "mouth"}
)

_PARENT_BY_SEMANTIC: dict[str, str | None] = {
    "body": None,
    "cloth": "body",
    "face": "body",
    "eye_white_l": "face",
    "eye_white_r": "face",
    "iris_l": "eye_white_l",
    "iris_r": "eye_white_r",
    "brow_l": "face",
    "brow_r": "face",
    "mouth": "face",
    "hair_front": "face",
    "hair_side_l": "face",
    "hair_side_r": "face",
    "hair_back": "body",
}


@dataclass(frozen=True, slots=True)
class SemanticRefinementConfig:
    mirror_confidence_scale: float = 0.72
    body_proxy_confidence_scale: float = 0.62
    side_hair_confidence_scale: float = 0.78
    side_hair_min_active_pixels: int = 12
    side_hair_outer_fraction: float = 0.18
    side_hair_min_y_fraction: float = 0.12

    def validate(self) -> None:
        for name, value in (
            ("mirror_confidence_scale", self.mirror_confidence_scale),
            ("body_proxy_confidence_scale", self.body_proxy_confidence_scale),
            ("side_hair_confidence_scale", self.side_hair_confidence_scale),
        ):
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite in (0,1]")
        if not isinstance(self.side_hair_min_active_pixels, int) or self.side_hair_min_active_pixels < 1:
            raise ValueError("side_hair_min_active_pixels must be a positive integer")
        if not 0 < self.side_hair_outer_fraction < 0.5:
            raise ValueError("side_hair_outer_fraction must be in (0,0.5)")
        if not 0 <= self.side_hair_min_y_fraction < 1:
            raise ValueError("side_hair_min_y_fraction must be in [0,1)")


def _layer_id(semantic: str) -> str:
    return semantic.replace("_", "-")


def _flip_rgba_h(width: int, height: int, rgba: bytes) -> bytes:
    out = bytearray(len(rgba))
    for y in range(height):
        for x in range(width):
            src = (y * width + x) * 4
            dst = (y * width + (width - 1 - x)) * 4
            out[dst:dst + 4] = rgba[src:src + 4]
    return bytes(out)


def _flip_a8_h(width: int, height: int, alpha: bytes) -> bytes:
    out = bytearray(len(alpha))
    for y in range(height):
        row = y * width
        for x in range(width):
            out[row + width - 1 - x] = alpha[row + x]
    return bytes(out)


def _mirror_record(
    source: NormalizedLayerRecordV1,
    asset: NormalizedLayerAssetV1,
    target_semantic: str,
    center_x: float,
    confidence_scale: float,
) -> tuple[NormalizedLayerRecordV1, NormalizedLayerAssetV1]:
    x, y, width, height = source.bbox
    mirrored_x = min(max(2.0 * center_x - (x + width), 0.0), max(0.0, 1.0 - width))
    layer_id = _layer_id(target_semantic)
    target = NormalizedLayerRecordV1(
        layer_id,
        target_semantic,
        f"layers/{layer_id}.rgba",
        f"masks/{layer_id}.a8",
        (mirrored_x, y, width, height),
        source.z_order + (1 if target_semantic.endswith("_r") else -1),
        min(1.0, source.confidence * confidence_scale),
        None,
    )
    target_asset = NormalizedLayerAssetV1(
        layer_id,
        target_semantic,
        asset.width,
        asset.height,
        _flip_rgba_h(asset.width, asset.height, asset.rgba),
        _flip_a8_h(asset.width, asset.height, asset.alpha),
    )
    return target, target_asset


def _body_proxy_from_cloth(
    cloth: NormalizedLayerRecordV1,
    cloth_asset: NormalizedLayerAssetV1,
    confidence_scale: float,
) -> tuple[NormalizedLayerRecordV1, NormalizedLayerAssetV1]:
    layer_id = "body"
    record = NormalizedLayerRecordV1(
        layer_id,
        "body",
        "layers/body.rgba",
        "masks/body.a8",
        cloth.bbox,
        cloth.z_order - 1,
        min(1.0, cloth.confidence * confidence_scale),
        None,
    )
    asset = NormalizedLayerAssetV1(
        layer_id,
        "body",
        cloth_asset.width,
        cloth_asset.height,
        cloth_asset.rgba,
        cloth_asset.alpha,
    )
    return record, asset


def _tight_subset(
    record: NormalizedLayerRecordV1,
    asset: NormalizedLayerAssetV1,
    *,
    keep,
    target_semantic: str,
    confidence_scale: float,
) -> tuple[NormalizedLayerRecordV1, NormalizedLayerAssetV1] | None:
    active: list[tuple[int, int]] = []
    for y in range(asset.height):
        for x in range(asset.width):
            idx = y * asset.width + x
            if asset.alpha[idx] > 0 and keep(x, y):
                active.append((x, y))
    if not active:
        return None
    min_x = min(x for x, _ in active); max_x = max(x for x, _ in active)
    min_y = min(y for _, y in active); max_y = max(y for _, y in active)
    width = max_x - min_x + 1; height = max_y - min_y + 1
    rgba = bytearray(width * height * 4)
    alpha = bytearray(width * height)
    for x, y in active:
        src_i = y * asset.width + x
        dst_i = (y - min_y) * width + (x - min_x)
        alpha[dst_i] = asset.alpha[src_i]
        rgba[dst_i * 4: dst_i * 4 + 4] = asset.rgba[src_i * 4: src_i * 4 + 4]
    bx, by, bw, bh = record.bbox
    sx = bw / asset.width; sy = bh / asset.height
    bbox = (bx + min_x * sx, by + min_y * sy, width * sx, height * sy)
    layer_id = _layer_id(target_semantic)
    target = NormalizedLayerRecordV1(
        layer_id, target_semantic,
        f"layers/{layer_id}.rgba", f"masks/{layer_id}.a8",
        bbox, record.z_order + 1,
        min(1.0, record.confidence * confidence_scale),
        None,
    )
    return target, NormalizedLayerAssetV1(
        layer_id, target_semantic, width, height, bytes(rgba), bytes(alpha)
    )


def _side_hair_from_source(
    source: NormalizedLayerRecordV1,
    asset: NormalizedLayerAssetV1,
    face: NormalizedLayerRecordV1,
    target_semantic: str,
    config: SemanticRefinementConfig,
) -> tuple[NormalizedLayerRecordV1, NormalizedLayerAssetV1] | None:
    fx, fy, fw, fh = face.bbox
    bx, by, bw, bh = source.bbox
    outer = config.side_hair_outer_fraction
    min_y = fy + fh * config.side_hair_min_y_fraction

    def keep_l(x: int, y: int) -> bool:
        gx = bx + (x + 0.5) / asset.width * bw
        gy = by + (y + 0.5) / asset.height * bh
        return gx <= fx + fw * outer and gy >= min_y

    def keep_r(x: int, y: int) -> bool:
        gx = bx + (x + 0.5) / asset.width * bw
        gy = by + (y + 0.5) / asset.height * bh
        return gx >= fx + fw * (1.0 - outer) and gy >= min_y

    result = _tight_subset(
        source, asset,
        keep=keep_l if target_semantic.endswith("_l") else keep_r,
        target_semantic=target_semantic,
        confidence_scale=config.side_hair_confidence_scale,
    )
    if result is None:
        return None
    _, out_asset = result
    active = sum(1 for value in out_asset.alpha if value > 0)
    if active < config.side_hair_min_active_pixels:
        return None
    return result


def _bbox_center_y(item: NormalizedLayerRecordV1) -> float:
    return item.bbox[1] + item.bbox[3] * 0.5


def _pair_consistency_findings(
    records: dict[str, NormalizedLayerRecordV1],
    face: NormalizedLayerRecordV1,
) -> list[DecomposerFindingV1]:
    findings: list[DecomposerFindingV1] = []
    for left, right in _PAIR_RULES:
        if left not in records or right not in records:
            continue
        l = records[left]; r = records[right]
        la = l.bbox[2] * l.bbox[3]; ra = r.bbox[2] * r.bbox[3]
        ratio = max(la, ra) / max(min(la, ra), 1e-9)
        dy = abs(_bbox_center_y(l) - _bbox_center_y(r))
        if ratio > 2.25 or dy > face.bbox[3] * 0.18:
            findings.append(DecomposerFindingV1(
                "warning", "semantic-pair-geometry-mismatch",
                f"{left}/{right} geometry differs beyond the pair-consistency threshold",
                f"{_layer_id(left)}+{_layer_id(right)}",
            ))
        if abs(l.confidence - r.confidence) > 0.30:
            findings.append(DecomposerFindingV1(
                "warning", "semantic-pair-confidence-mismatch",
                f"{left}/{right} confidence differs by more than 0.30",
                f"{_layer_id(left)}+{_layer_id(right)}",
            ))
    return findings


def _replace_z(item: NormalizedLayerRecordV1, z_order: int) -> NormalizedLayerRecordV1:
    return NormalizedLayerRecordV1(
        item.id, item.semantic, item.image_uri, item.mask_uri, item.bbox,
        z_order, item.confidence, item.parent_id,
    )


def _repair_core_z_order(
    records: dict[str, NormalizedLayerRecordV1],
) -> list[DecomposerFindingV1]:
    findings: list[DecomposerFindingV1] = []

    def ensure_before(back: str, front: str) -> None:
        if back not in records or front not in records:
            return
        if records[back].z_order >= records[front].z_order:
            records[back] = _replace_z(records[back], records[front].z_order - 1)
            findings.append(DecomposerFindingV1(
                "warning", "semantic-z-order-corrected",
                f"{back} was moved behind {front} to satisfy the A2D visual contract",
                _layer_id(back),
            ))

    def ensure_after(front: str, back: str) -> None:
        if front not in records or back not in records:
            return
        if records[front].z_order <= records[back].z_order:
            records[front] = _replace_z(records[front], records[back].z_order + 1)
            findings.append(DecomposerFindingV1(
                "warning", "semantic-z-order-corrected",
                f"{front} was moved in front of {back} to satisfy the A2D visual contract",
                _layer_id(front),
            ))

    ensure_before("hair_back", "body")
    ensure_before("body", "cloth")
    ensure_after("face", "body")
    for semantic in ("eye_white_l", "eye_white_r", "mouth", "brow_l", "brow_r", "hair_front"):
        ensure_after(semantic, "face")
    ensure_after("iris_l", "eye_white_l")
    ensure_after("iris_r", "eye_white_r")
    return findings


def _apply_canonical_parents(
    records: dict[str, NormalizedLayerRecordV1],
) -> dict[str, NormalizedLayerRecordV1]:
    present = set(records)
    out: dict[str, NormalizedLayerRecordV1] = {}
    for semantic, item in records.items():
        requested = _PARENT_BY_SEMANTIC.get(semantic, item.parent_id)
        parent_id = _layer_id(requested) if requested in present else None
        out[semantic] = NormalizedLayerRecordV1(
            item.id, item.semantic, item.image_uri, item.mask_uri, item.bbox,
            item.z_order, item.confidence, parent_id,
        )
    return out


def _revision(previous: str, config: SemanticRefinementConfig) -> str:
    digest = hashlib.sha256()
    digest.update(previous.encode("utf-8"))
    digest.update(repr(config).encode("utf-8"))
    digest.update(b"p3-r3-semantic-refinement-v1")
    return f"sha256:{digest.hexdigest()}"


def refine_decomposer_result(
    result: DecomposerResultV1,
    source_image: SourceImageRgba,
    *,
    config: SemanticRefinementConfig | None = None,
) -> DecomposerResultV1:
    """Complete only semantics that can be deterministically inferred.

    Synthetic layers are explicitly down-weighted and reported. Required
    semantics that remain unavailable become blocking findings.
    """
    config = config or SemanticRefinementConfig()
    config.validate()
    source_image.validate()
    if source_image.width != result.canvas_width or source_image.height != result.canvas_height:
        raise ValueError("source image dimensions do not match decomposer result")

    assets_by_id = {item.layer_id: item for item in result.assets}
    records = {item.semantic: item for item in result.layers if item.semantic != "accessory"}
    accessories = [item for item in result.layers if item.semantic == "accessory"]
    accessory_assets = [assets_by_id[item.id] for item in accessories]

    assets: dict[str, NormalizedLayerAssetV1] = {
        item.semantic: assets_by_id[item.id]
        for item in result.layers if item.semantic != "accessory"
    }
    findings = list(result.findings)

    if "body" not in records and "cloth" in records:
        body_record, body_asset = _body_proxy_from_cloth(
            records["cloth"], assets["cloth"], config.body_proxy_confidence_scale
        )
        records["body"] = body_record; assets["body"] = body_asset
        findings.append(DecomposerFindingV1(
            "warning", "body-proxy-synthesized",
            "body was synthesized from the cloth matte; anatomy completion remains a P3-R4 concern",
            "body",
        ))

    face = records.get("face")
    if face is not None:
        center_x = face.bbox[0] + face.bbox[2] * 0.5
        for left, right in _PAIR_RULES:
            has_l, has_r = left in records, right in records
            if has_l ^ has_r:
                source_semantic = left if has_l else right
                target_semantic = right if has_l else left
                mirrored_record, mirrored_asset = _mirror_record(
                    records[source_semantic], assets[source_semantic],
                    target_semantic, center_x, config.mirror_confidence_scale,
                )
                records[target_semantic] = mirrored_record
                assets[target_semantic] = mirrored_asset
                findings.append(DecomposerFindingV1(
                    "warning", "semantic-pair-mirrored",
                    f"{target_semantic} was mirrored from {source_semantic}",
                    _layer_id(target_semantic),
                ))

        for target in ("hair_side_l", "hair_side_r"):
            if target in records:
                continue
            generated = None
            for source_semantic in ("hair_front", "hair_back"):
                if source_semantic in records:
                    generated = _side_hair_from_source(
                        records[source_semantic], assets[source_semantic],
                        face, target, config,
                    )
                    if generated is not None:
                        break
            if generated is not None:
                new_record, new_asset = generated
                records[target] = new_record; assets[target] = new_asset
                findings.append(DecomposerFindingV1(
                    "warning", "side-hair-synthesized",
                    f"{target} was extracted from existing hair pixels",
                    new_record.id,
                ))

    if face is not None:
        findings.extend(_pair_consistency_findings(records, face))
    findings.extend(_repair_core_z_order(records))

    missing = sorted(_REQUIRED - set(records))
    for semantic in missing:
        findings.append(DecomposerFindingV1(
            "error", "required-semantic-missing",
            f"required semantic {semantic} could not be refined",
            _layer_id(semantic),
        ))

    records = _apply_canonical_parents(records)
    layers = list(records.values()) + accessories
    out_assets = list(assets.values()) + accessory_assets
    layers.sort(key=lambda item: (item.z_order, item.id))
    out_assets.sort(key=lambda item: item.layer_id)
    findings.sort(key=lambda item: (
        {"error": 0, "warning": 1, "info": 2}.get(item.severity, 3),
        item.code, item.subject_id or "", item.message,
    ))
    return DecomposerResultV1(
        result.version,
        result.character_id,
        _revision(result.source_revision, config),
        result.canvas_width,
        result.canvas_height,
        tuple(layers),
        result.landmarks,
        tuple(out_assets),
        tuple(findings),
    )
