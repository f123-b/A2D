from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contract import DecomposerResultV1, SourceImageRgba
from .pipeline import DecomposerConfig, decompose_image
from .production import EncodedImageDecoder, decode_source_image


@dataclass(frozen=True, slots=True)
class RigCompilerBridgeInputV1:
    value: Any
    masks: Mapping[str, Any]
    images: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SingleImageCompileResultV1:
    decomposer: DecomposerResultV1
    compiler: Any | None


def to_rig_compiler_inputs(result: DecomposerResultV1) -> RigCompilerBridgeInputV1:
    """Convert P3 normalized output to the existing P2 one-click compiler ABI.

    Imports are intentionally local so the decomposer package remains usable as
    a standalone zero-dependency normalization service.
    """
    if not result.ready:
        raise ValueError("decomposer result is not ready")
    from a2d_rig_compiler import (
        AlphaMask,
        Landmark,
        NormalizedRect,
        NormalizedRigInput,
        RgbaImage,
        Semantic,
        SemanticLayer,
    )

    asset_by_id = {item.layer_id: item for item in result.assets}
    if len(asset_by_id) != len(result.assets):
        raise ValueError("decomposer result contains duplicate layer assets")

    layers = []
    masks: dict[str, Any] = {}
    images: dict[str, Any] = {}
    for record in result.layers:
        asset = asset_by_id.get(record.id)
        if asset is None:
            raise ValueError(f"missing normalized asset for layer {record.id}")
        if asset.width < 2 or asset.height < 2:
            raise ValueError(
                f"normalized asset {record.id} is too small for P2 mesh generation"
            )
        x, y, width, height = record.bbox
        layers.append(SemanticLayer(
            id=record.id,
            semantic=Semantic(record.semantic),
            image_uri=record.image_uri,
            bbox=NormalizedRect(x, y, width, height),
            z_order=record.z_order,
            parent_id=record.parent_id,
            mask_uri=record.mask_uri,
            confidence=record.confidence,
        ))
        masks[record.id] = AlphaMask.from_u8(asset.width, asset.height, asset.alpha)
        images[record.id] = RgbaImage(asset.width, asset.height, asset.rgba)

    landmarks = tuple(
        Landmark(item.id, item.x, item.y, item.confidence)
        for item in result.landmarks
    )
    value = NormalizedRigInput(
        result.character_id,
        result.canvas_width,
        result.canvas_height,
        tuple(layers),
        landmarks,
        result.source_revision,
    )
    return RigCompilerBridgeInputV1(value, masks, images)


def decompose_and_compile(
    character_id: str,
    image: SourceImageRgba,
    backend: Any,
    *,
    decomposer_config: DecomposerConfig | None = None,
    qa_config: Any | None = None,
    atlas_config: Any | None = None,
) -> SingleImageCompileResultV1:
    """Run P3 normalization then P2 one-click compilation."""
    decomposed = decompose_image(
        character_id,
        image,
        backend,
        config=decomposer_config,
    )
    if not decomposed.ready:
        return SingleImageCompileResultV1(decomposed, None)
    bridged = to_rig_compiler_inputs(decomposed)
    from a2d_rig_compiler import compile_avatar
    compiled = compile_avatar(
        bridged.value,
        bridged.masks,
        bridged.images,
        qa_config=qa_config,
        atlas_config=atlas_config,
    )
    return SingleImageCompileResultV1(decomposed, compiled)


def decode_decompose_and_compile(
    character_id: str,
    payload: bytes,
    backend: Any,
    *,
    decoder: EncodedImageDecoder | None = None,
    decomposer_config: DecomposerConfig | None = None,
    qa_config: Any | None = None,
    atlas_config: Any | None = None,
) -> SingleImageCompileResultV1:
    image = decode_source_image(payload, decoder=decoder)
    return decompose_and_compile(
        character_id,
        image,
        backend,
        decomposer_config=decomposer_config,
        qa_config=qa_config,
        atlas_config=atlas_config,
    )
