from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import math
from typing import Protocol

from .contract import (
    DecomposerFindingV1,
    DecomposerResultV1,
    NormalizedLayerAssetV1,
    NormalizedLayerRecordV1,
    SourceImageRgba,
)


@dataclass(frozen=True, slots=True)
class CompletionRequestV1:
    layer_id: str
    semantic: str
    bbox: tuple[float, float, float, float]
    width: int
    height: int
    visible_rgba: bytes
    visible_alpha: bytes
    completion_mask: bytes
    source_image: SourceImageRgba

    def validate(self) -> None:
        if not self.layer_id or not self.semantic:
            raise ValueError("completion request layer_id/semantic are required")
        if self.width < 1 or self.height < 1:
            raise ValueError("completion request dimensions must be positive")
        count = self.width * self.height
        if len(self.visible_rgba) != count * 4:
            raise ValueError("completion request RGBA length mismatch")
        if len(self.visible_alpha) != count:
            raise ValueError("completion request alpha length mismatch")
        if len(self.completion_mask) != count:
            raise ValueError("completion request mask length mismatch")
        x, y, w, h = self.bbox
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            raise ValueError("completion request bbox must be finite")
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1 or y + h > 1:
            raise ValueError("completion request bbox must remain inside normalized canvas")
        self.source_image.validate()


@dataclass(frozen=True, slots=True)
class CompletionResponseV1:
    rgba: bytes
    confidence: float


class CompletionProvider(Protocol):
    provider_name: str
    provider_revision: str

    def complete(self, request: CompletionRequestV1) -> CompletionResponseV1: ...


@dataclass(frozen=True, slots=True)
class OcclusionCompletionConfig:
    occluder_alpha_threshold: int = 16
    target_hole_alpha_threshold: int = 8
    min_completion_pixels: int = 8
    low_confidence_threshold: float = 0.65
    body_proxy_requires_completion: bool = True

    def validate(self) -> None:
        for name, value in (
            ("occluder_alpha_threshold", self.occluder_alpha_threshold),
            ("target_hole_alpha_threshold", self.target_hole_alpha_threshold),
        ):
            if not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"{name} must be an integer in 0..255")
        if not isinstance(self.min_completion_pixels, int) or self.min_completion_pixels < 1:
            raise ValueError("min_completion_pixels must be a positive integer")
        if not math.isfinite(self.low_confidence_threshold) or not 0 <= self.low_confidence_threshold <= 1:
            raise ValueError("low_confidence_threshold must be finite in [0,1]")


class DeterministicReferenceCompletionProvider:
    """Dependency-free correctness oracle, not a production inpainting model."""

    provider_name = "a2d-reference-completion"
    provider_revision = "1"

    def complete(self, request: CompletionRequestV1) -> CompletionResponseV1:
        request.validate()
        width, height = request.width, request.height
        count = width * height
        out = bytearray(request.visible_rgba)
        owner = [-1] * count
        queue: deque[int] = deque()

        for i in range(count):
            if request.completion_mask[i] == 0 and request.visible_alpha[i] > 0:
                owner[i] = i
                queue.append(i)

        while queue:
            i = queue.popleft()
            x = i % width
            y = i // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                ni = ny * width + nx
                if owner[ni] != -1:
                    continue
                owner[ni] = owner[i]
                queue.append(ni)

        for i in range(count):
            if request.completion_mask[i] == 0:
                continue
            src = owner[i]
            if src >= 0:
                out[i * 4:i * 4 + 4] = request.visible_rgba[src * 4:src * 4 + 4]
                out[i * 4 + 3] = 255
            else:
                out[i * 4:i * 4 + 4] = bytes((128, 128, 128, 255))

        return CompletionResponseV1(bytes(out), 0.50)


_TARGET_OCCLUDERS: dict[str, tuple[str, ...]] = {
    "face": ("hair_front", "hair_side_l", "hair_side_r"),
    "body": ("cloth",),
}


def _project_occluder(
    target: NormalizedLayerRecordV1,
    target_asset: NormalizedLayerAssetV1,
    occluder: NormalizedLayerRecordV1,
    occluder_asset: NormalizedLayerAssetV1,
    config: OcclusionCompletionConfig,
) -> bytes:
    tx, ty, tw, th = target.bbox
    ox, oy, ow, oh = occluder.bbox
    mask = bytearray(target_asset.width * target_asset.height)
    if tw <= 0 or th <= 0 or ow <= 0 or oh <= 0:
        return bytes(mask)

    for y in range(target_asset.height):
        gy = ty + (y + 0.5) / target_asset.height * th
        if gy < oy or gy >= oy + oh:
            continue
        ov = (gy - oy) / oh
        oy_i = min(occluder_asset.height - 1, max(0, int(ov * occluder_asset.height)))
        for x in range(target_asset.width):
            idx = y * target_asset.width + x
            if target_asset.alpha[idx] > config.target_hole_alpha_threshold:
                continue
            gx = tx + (x + 0.5) / target_asset.width * tw
            if gx < ox or gx >= ox + ow:
                continue
            ou = (gx - ox) / ow
            ox_i = min(occluder_asset.width - 1, max(0, int(ou * occluder_asset.width)))
            oidx = oy_i * occluder_asset.width + ox_i
            if occluder_asset.alpha[oidx] >= config.occluder_alpha_threshold:
                mask[idx] = 255
    return bytes(mask)


def _or_masks(masks: list[bytes], count: int) -> bytes:
    out = bytearray(count)
    for mask in masks:
        if len(mask) != count:
            raise ValueError("internal completion mask length mismatch")
        for i, value in enumerate(mask):
            if value:
                out[i] = 255
    return bytes(out)


def _body_is_proxy(result: DecomposerResultV1) -> bool:
    return any(
        item.code == "body-proxy-synthesized" and item.subject_id == "body"
        for item in result.findings
    )


def _completion_mask_for(
    semantic: str,
    record: NormalizedLayerRecordV1,
    asset: NormalizedLayerAssetV1,
    records: dict[str, NormalizedLayerRecordV1],
    assets: dict[str, NormalizedLayerAssetV1],
    result: DecomposerResultV1,
    config: OcclusionCompletionConfig,
) -> bytes:
    count = asset.width * asset.height
    if semantic == "body" and config.body_proxy_requires_completion and _body_is_proxy(result):
        return bytes([255]) * count

    masks: list[bytes] = []
    for occluder_semantic in _TARGET_OCCLUDERS.get(semantic, ()):
        occ_record = records.get(occluder_semantic)
        occ_asset = assets.get(occluder_semantic)
        if occ_record is None or occ_asset is None:
            continue
        masks.append(_project_occluder(record, asset, occ_record, occ_asset, config))
    return _or_masks(masks, count)


def _validate_provider_identity(provider: CompletionProvider) -> tuple[str, str]:
    name = getattr(provider, "provider_name", "")
    revision = getattr(provider, "provider_revision", "")
    if not isinstance(name, str) or not name:
        raise ValueError("completion provider_name is required")
    if not isinstance(revision, str) or not revision:
        raise ValueError("completion provider_revision is required")
    return name, revision


def _protected_pixels_unchanged(original: bytes, completed: bytes, completion_mask: bytes) -> bool:
    for i, value in enumerate(completion_mask):
        if value != 0:
            continue
        start = i * 4
        if original[start:start + 4] != completed[start:start + 4]:
            return False
    return True


def _revision(
    previous: str,
    config: OcclusionCompletionConfig,
    provider_name: str,
    provider_revision: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(previous.encode("utf-8"))
    digest.update(repr(config).encode("utf-8"))
    digest.update(provider_name.encode("utf-8"))
    digest.update(provider_revision.encode("utf-8"))
    digest.update(b"p3-r4-occlusion-completion-v1")
    return f"sha256:{digest.hexdigest()}"


def complete_occlusions(
    result: DecomposerResultV1,
    source_image: SourceImageRgba,
    provider: CompletionProvider | None,
    *,
    config: OcclusionCompletionConfig | None = None,
) -> DecomposerResultV1:
    """Complete hidden target pixels while protecting known visible pixels."""
    config = config or OcclusionCompletionConfig()
    config.validate()
    source_image.validate()
    if source_image.width != result.canvas_width or source_image.height != result.canvas_height:
        raise ValueError("source image dimensions do not match decomposer result")

    records = {item.semantic: item for item in result.layers if item.semantic != "accessory"}
    assets_by_id = {item.layer_id: item for item in result.assets}
    assets = {
        semantic: assets_by_id[record.id]
        for semantic, record in records.items()
        if record.id in assets_by_id
    }
    out_assets = dict(assets)
    findings = list(result.findings)

    provider_name = "none"
    provider_revision = "none"
    if provider is not None:
        provider_name, provider_revision = _validate_provider_identity(provider)

    for semantic in ("face", "body"):
        record = records.get(semantic)
        asset = assets.get(semantic)
        if record is None or asset is None:
            continue

        completion_mask = _completion_mask_for(
            semantic, record, asset, records, assets, result, config
        )
        active = sum(1 for value in completion_mask if value)
        if active < config.min_completion_pixels:
            continue

        findings.append(DecomposerFindingV1(
            "info", "occlusion-completion-required",
            f"{semantic} has {active} pixels requiring completion", record.id,
        ))

        if provider is None:
            findings.append(DecomposerFindingV1(
                "warning", "completion-provider-missing",
                f"{semantic} requires completion but no CompletionProvider was supplied", record.id,
            ))
            continue

        request = CompletionRequestV1(
            record.id, semantic, record.bbox, asset.width, asset.height,
            asset.rgba, asset.alpha, completion_mask, source_image,
        )
        try:
            response = provider.complete(request)
        except Exception as exc:
            findings.append(DecomposerFindingV1(
                "error", "completion-provider-error",
                f"{semantic} completion provider failed: {type(exc).__name__}: {exc}", record.id,
            ))
            continue

        if len(response.rgba) != asset.width * asset.height * 4:
            findings.append(DecomposerFindingV1(
                "error", "completion-output-size-invalid",
                f"{semantic} completion RGBA length does not match target dimensions", record.id,
            ))
            continue
        if not math.isfinite(response.confidence) or not 0 <= response.confidence <= 1:
            findings.append(DecomposerFindingV1(
                "error", "completion-confidence-invalid",
                f"{semantic} completion confidence must be finite in [0,1]", record.id,
            ))
            continue
        if not _protected_pixels_unchanged(asset.rgba, response.rgba, completion_mask):
            findings.append(DecomposerFindingV1(
                "error", "completion-visible-pixel-mutated",
                f"{semantic} completion modified pixels outside the allowed completion mask", record.id,
            ))
            continue

        alpha = bytearray(asset.alpha)
        for i, value in enumerate(completion_mask):
            if value:
                alpha[i] = response.rgba[i * 4 + 3]
        out_assets[semantic] = NormalizedLayerAssetV1(
            asset.layer_id, asset.semantic, asset.width, asset.height,
            response.rgba, bytes(alpha),
        )
        findings.append(DecomposerFindingV1(
            "info", "occlusion-completed",
            f"{semantic} completion filled {active} pixels using {provider_name}@{provider_revision}",
            record.id,
        ))
        if response.confidence < config.low_confidence_threshold:
            findings.append(DecomposerFindingV1(
                "warning", "completion-low-confidence",
                f"{semantic} completion confidence {response.confidence:.3f} is below "
                f"{config.low_confidence_threshold:.3f}", record.id,
            ))

    accessories = [item for item in result.layers if item.semantic == "accessory"]
    accessory_assets = [assets_by_id[item.id] for item in accessories if item.id in assets_by_id]
    final_assets = list(out_assets.values()) + accessory_assets
    final_assets.sort(key=lambda item: item.layer_id)
    findings.sort(key=lambda item: (
        {"error": 0, "warning": 1, "info": 2}.get(item.severity, 3),
        item.code, item.subject_id or "", item.message,
    ))
    return DecomposerResultV1(
        result.version, result.character_id,
        _revision(result.source_revision, config, provider_name, provider_revision),
        result.canvas_width, result.canvas_height, result.layers, result.landmarks,
        tuple(final_assets), tuple(findings),
    )
