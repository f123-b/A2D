from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from typing import Protocol, Sequence
import zlib

from .contract import (
    BackendDecompositionV1,
    BackendLayerObservationV1,
    PixelRect,
    SourceImageRgba,
)


SEE_THROUGH_SCRIPT = "inference/scripts/inference_psd.py"
SEE_THROUGH_V3_REFERENCE_REVISION = "7f139bb25c46a0c8ac720d95ddab185fcda5451c"


class ProductionAdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessResultV1:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProcessRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResultV1: ...


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResultV1:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            timeout=timeout_seconds,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return ProcessResultV1(completed.returncode, completed.stdout, completed.stderr)


class EncodedImageDecoder(Protocol):
    def decode(self, payload: bytes) -> SourceImageRgba: ...


class RgbaRasterCodec(Protocol):
    def read_rgba(self, path: Path) -> SourceImageRgba: ...
    def crop(self, image: SourceImageRgba, rect: PixelRect) -> SourceImageRgba: ...
    def resize(self, image: SourceImageRgba, width: int, height: int) -> SourceImageRgba: ...


class PillowImageCodec:
    """Production image codec. Pillow is imported lazily so zero-dependency CI still works."""

    @staticmethod
    def _image_module():
        try:
            from PIL import Image
        except ImportError as exc:
            raise ProductionAdapterError(
                "Pillow is required for production PNG/JPG decoding; install a2d-decomposer[production]"
            ) from exc
        return Image

    def decode(self, payload: bytes) -> SourceImageRgba:
        if not payload:
            raise ProductionAdapterError("encoded image payload is empty")
        import io
        Image = self._image_module()
        try:
            with Image.open(io.BytesIO(payload)) as decoded:
                rgba = decoded.convert("RGBA")
                out = SourceImageRgba(rgba.width, rgba.height, rgba.tobytes())
        except Exception as exc:
            raise ProductionAdapterError(f"failed to decode input image: {exc}") from exc
        out.validate()
        return out

    def read_rgba(self, path: Path) -> SourceImageRgba:
        Image = self._image_module()
        try:
            with Image.open(path) as decoded:
                rgba = decoded.convert("RGBA")
                out = SourceImageRgba(rgba.width, rgba.height, rgba.tobytes())
        except Exception as exc:
            raise ProductionAdapterError(f"failed to read See-through layer {path}: {exc}") from exc
        out.validate()
        return out

    def crop(self, image: SourceImageRgba, rect: PixelRect) -> SourceImageRgba:
        image.validate()
        rect.validate(image.width, image.height)
        Image = self._image_module()
        src = Image.frombytes("RGBA", (image.width, image.height), image.pixels)
        cropped = src.crop((rect.x, rect.y, rect.x + rect.width, rect.y + rect.height))
        return SourceImageRgba(cropped.width, cropped.height, cropped.tobytes())

    def resize(self, image: SourceImageRgba, width: int, height: int) -> SourceImageRgba:
        image.validate()
        if width < 1 or height < 1:
            raise ProductionAdapterError("resize target must be positive")
        Image = self._image_module()
        src = Image.frombytes("RGBA", (image.width, image.height), image.pixels)
        resampling = getattr(Image, "Resampling", Image)
        resized = src.resize((width, height), resample=resampling.LANCZOS)
        return SourceImageRgba(width, height, resized.tobytes())


@dataclass(frozen=True, slots=True)
class SeeThroughConfig:
    repo_root: str
    python_executable: str = sys.executable
    seed: int = 42
    resolution: int = 1280
    resolution_depth: int = 768
    inference_steps: int = 30
    inference_steps_depth: int = -1
    layerdiff_repo_id: str = "layerdifforg/seethroughv0.0.2_layerdiff3d"
    depth_repo_id: str = "24yearsold/seethroughv0.0.1_marigold"
    tblr_split: bool = True
    group_offload: bool = False
    timeout_seconds: float = 1800.0
    backend_revision: str = SEE_THROUGH_V3_REFERENCE_REVISION

    def validate(self) -> None:
        if not self.repo_root:
            raise ValueError("See-through repo_root is required")
        if not self.python_executable:
            raise ValueError("python_executable is required")
        if not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if self.resolution < 128 or self.resolution > 8192:
            raise ValueError("resolution must be in 128..8192")
        if self.resolution_depth != -1 and not 128 <= self.resolution_depth <= 8192:
            raise ValueError("resolution_depth must be -1 or in 128..8192")
        if self.inference_steps < 1:
            raise ValueError("inference_steps must be >= 1")
        if self.inference_steps_depth < -1:
            raise ValueError("inference_steps_depth must be >= -1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")


_SEE_THROUGH_SEMANTIC: dict[str, str] = {
    "face": "face",
    "mouth": "mouth",
    "eyewhite-l": "eye_white_l",
    "eyewhite-r": "eye_white_r",
    "eyewhitel": "eye_white_l",
    "eyewhiter": "eye_white_r",
    "irides-l": "iris_l",
    "irides-r": "iris_r",
    "iridesl": "iris_l",
    "iridesr": "iris_r",
    "eyebrow-l": "brow_l",
    "eyebrow-r": "brow_r",
    "eyebrowl": "brow_l",
    "eyebrowr": "brow_r",
    "browl": "brow_l",
    "browr": "brow_r",
    "hairf": "hair_front",
    "hairb": "hair_back",
    "front hair": "hair_front",
    "back hair": "hair_back",
    "topwear": "cloth",
    "headwear": "accessory",
    "eyewear": "accessory",
    "earwear": "accessory",
    "tail": "accessory",
    "wings": "accessory",
    "objects": "accessory",
}

_PARENT_SEMANTIC: dict[str, str] = {
    "eye_white_l": "face",
    "eye_white_r": "face",
    "iris_l": "eye_white_l",
    "iris_r": "eye_white_r",
    "brow_l": "face",
    "brow_r": "face",
    "mouth": "face",
    "hair_front": "face",
    "hair_back": "face",
}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(payload, crc)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc & 0xFFFFFFFF)


def encode_rgba_png(image: SourceImageRgba) -> bytes:
    """Dependency-free RGBA8 PNG encoder used for the See-through subprocess input."""
    image.validate()
    raw = bytearray()
    stride = image.width * 4
    for y in range(image.height):
        raw.append(0)
        start = y * stride
        raw.extend(image.pixels[start:start + stride])
    ihdr = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
        + _png_chunk(b"IEND", b"")
    )


def _normalize_tag(tag: str) -> str:
    return " ".join(tag.strip().lower().replace("_", " ").split())


def _semantic_for_tag(tag: str) -> str:
    normalized = _normalize_tag(tag)
    direct = _SEE_THROUGH_SEMANTIC.get(normalized)
    if direct is not None:
        return direct
    return normalized.replace(" ", "_")


def _xyxy(value: object, *, tag: str, frame_width: int, frame_height: int) -> PixelRect:
    if not isinstance(value, list) or len(value) != 4:
        raise ProductionAdapterError(f"See-through part {tag}: xyxy must contain four values")
    if not all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in value):
        raise ProductionAdapterError(f"See-through part {tag}: xyxy must be finite numeric values")
    x0, y0, x1, y1 = (int(round(float(v))) for v in value)
    if x1 <= x0 or y1 <= y0:
        raise ProductionAdapterError(f"See-through part {tag}: xyxy has non-positive extent")
    rect = PixelRect(x0, y0, x1 - x0, y1 - y0)
    rect.validate(frame_width, frame_height)
    return rect


@dataclass(frozen=True, slots=True)
class _CanvasTransform:
    model_width: int
    model_height: int
    source_width: int
    source_height: int
    content_x0: float
    content_y0: float
    content_x1: float
    content_y1: float

    @classmethod
    def create(
        cls,
        model_width: int,
        model_height: int,
        source_width: int,
        source_height: int,
    ) -> "_CanvasTransform":
        if model_width < 1 or model_height < 1:
            raise ProductionAdapterError("See-through frame_size must be positive")
        if model_width == model_height and source_width != source_height:
            side = max(source_width, source_height)
            scale = model_width / side
            content_width = source_width * scale
            content_height = source_height * scale
            x0 = (model_width - content_width) * 0.5
            y0 = (model_height - content_height) * 0.5
            return cls(
                model_width, model_height, source_width, source_height,
                x0, y0, x0 + content_width, y0 + content_height,
            )
        return cls(
            model_width, model_height, source_width, source_height,
            0.0, 0.0, float(model_width), float(model_height),
        )

    def intersect_model_rect(self, rect: PixelRect) -> tuple[PixelRect, PixelRect]:
        x0 = max(float(rect.x), self.content_x0)
        y0 = max(float(rect.y), self.content_y0)
        x1 = min(float(rect.x + rect.width), self.content_x1)
        y1 = min(float(rect.y + rect.height), self.content_y1)
        if x1 <= x0 or y1 <= y0:
            raise ProductionAdapterError("See-through part falls entirely inside square-padding area")

        crop_x0 = max(0, int(math.floor(x0 - rect.x)))
        crop_y0 = max(0, int(math.floor(y0 - rect.y)))
        crop_x1 = min(rect.width, int(math.ceil(x1 - rect.x)))
        crop_y1 = min(rect.height, int(math.ceil(y1 - rect.y)))
        crop = PixelRect(crop_x0, crop_y0, crop_x1 - crop_x0, crop_y1 - crop_y0)

        sx = self.source_width / (self.content_x1 - self.content_x0)
        sy = self.source_height / (self.content_y1 - self.content_y0)
        src_x0 = max(0, int(math.floor((x0 - self.content_x0) * sx)))
        src_y0 = max(0, int(math.floor((y0 - self.content_y0) * sy)))
        src_x1 = min(self.source_width, int(math.ceil((x1 - self.content_x0) * sx)))
        src_y1 = min(self.source_height, int(math.ceil((y1 - self.content_y0) * sy)))
        source = PixelRect(src_x0, src_y0, max(1, src_x1 - src_x0), max(1, src_y1 - src_y0))
        source.validate(self.source_width, self.source_height)
        return crop, source


def _alpha_from_rgba(image: SourceImageRgba) -> bytes:
    return bytes(image.pixels[index] for index in range(3, len(image.pixels), 4))


def _parse_frame_size(value: object) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ProductionAdapterError("See-through info.json frame_size must be [height,width]")
    height, width = value
    if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
        raise ProductionAdapterError("See-through info.json frame_size must contain positive integers")
    return width, height


def _depth(value: object) -> float:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return 1.0


class SeeThroughProcessBackend:
    """Production adapter for the public See-through V3 command-line pipeline.

    It invokes the official script without ``--save_to_psd`` and consumes the
    stable ``optimized/info.json`` plus per-part PNG files written by
    ``further_extr``.
    """

    def __init__(
        self,
        config: SeeThroughConfig,
        *,
        runner: ProcessRunner | None = None,
        raster_codec: RgbaRasterCodec | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.runner = runner or SubprocessRunner()
        self.raster_codec = raster_codec or PillowImageCodec()

    def _command(self, source_path: Path, save_dir: Path) -> tuple[str, ...]:
        cfg = self.config
        command = [
            cfg.python_executable,
            SEE_THROUGH_SCRIPT,
            "--srcp", str(source_path),
            "--save_dir", str(save_dir),
            "--seed", str(cfg.seed),
            "--repo_id_layerdiff", cfg.layerdiff_repo_id,
            "--repo_id_depth", cfg.depth_repo_id,
            "--resolution", str(cfg.resolution),
            "--resolution_depth", str(cfg.resolution_depth),
            "--inference_steps", str(cfg.inference_steps),
            "--inference_steps_depth", str(cfg.inference_steps_depth),
            "--disable_progressbar",
        ]
        if cfg.tblr_split:
            command.append("--tblr_split")
        if cfg.group_offload:
            command.append("--group_offload")
        return tuple(command)

    def _parse_output(
        self,
        image: SourceImageRgba,
        optimized: Path,
    ) -> BackendDecompositionV1:
        info_path = optimized / "info.json"
        if not info_path.is_file():
            raise ProductionAdapterError(f"See-through output missing {info_path}")
        try:
            payload = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductionAdapterError(f"failed to read See-through info.json: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("parts"), dict):
            raise ProductionAdapterError("See-through info.json must contain an object 'parts'")
        model_width, model_height = _parse_frame_size(payload.get("frame_size"))
        transform = _CanvasTransform.create(
            model_width, model_height, image.width, image.height
        )

        raw_parts: list[tuple[str, str, dict[str, object], float]] = []
        for tag, raw_meta in payload["parts"].items():
            if not isinstance(tag, str) or not isinstance(raw_meta, dict):
                raise ProductionAdapterError("See-through parts must map string tags to objects")
            semantic = _semantic_for_tag(tag)
            raw_parts.append((tag, semantic, raw_meta, _depth(raw_meta.get("depth_median"))))

        ordered = sorted(raw_parts, key=lambda item: (-item[3], _normalize_tag(item[0])))
        z_by_tag = {tag: index for index, (tag, _, _, _) in enumerate(ordered)}

        source_key_by_semantic: dict[str, str] = {}
        for tag, semantic, _, _ in ordered:
            if semantic != "accessory" and semantic not in source_key_by_semantic:
                source_key_by_semantic[semantic] = tag

        observations: list[BackendLayerObservationV1] = []
        for tag, semantic, meta, _ in ordered:
            model_rect = _xyxy(
                meta.get("xyxy"),
                tag=tag,
                frame_width=model_width,
                frame_height=model_height,
            )
            layer_path = optimized / f"{tag}.png"
            if not layer_path.is_file():
                raise ProductionAdapterError(f"See-through part image missing: {layer_path}")
            raster = self.raster_codec.read_rgba(layer_path)
            if raster.width != model_rect.width or raster.height != model_rect.height:
                raise ProductionAdapterError(
                    f"See-through part {tag}: PNG size {raster.width}x{raster.height} "
                    f"does not match xyxy {model_rect.width}x{model_rect.height}"
                )
            crop_rect, source_rect = transform.intersect_model_rect(model_rect)
            if (
                crop_rect.x != 0 or crop_rect.y != 0
                or crop_rect.width != raster.width or crop_rect.height != raster.height
            ):
                raster = self.raster_codec.crop(raster, crop_rect)
            if raster.width != source_rect.width or raster.height != source_rect.height:
                raster = self.raster_codec.resize(raster, source_rect.width, source_rect.height)

            parent_semantic = _PARENT_SEMANTIC.get(semantic)
            parent_source_key = (
                source_key_by_semantic.get(parent_semantic)
                if parent_semantic is not None else None
            )
            observations.append(BackendLayerObservationV1(
                source_key=tag,
                semantic_label=semantic,
                bbox=source_rect,
                rgba=raster.pixels,
                alpha=_alpha_from_rgba(raster),
                z_order=z_by_tag[tag],
                confidence=1.0,
                parent_source_key=parent_source_key,
            ))

        return BackendDecompositionV1(
            tuple(observations),
            (),
            backend_name="see-through",
            backend_revision=self.config.backend_revision,
        )

    def decompose(self, image: SourceImageRgba) -> BackendDecompositionV1:
        image.validate()
        repo_root = Path(self.config.repo_root).expanduser().resolve()
        script = repo_root / SEE_THROUGH_SCRIPT
        if not script.is_file():
            raise ProductionAdapterError(
                f"See-through script not found: {script}; pin/setup the upstream repository first"
            )
        with tempfile.TemporaryDirectory(prefix="a2d-seethrough-") as temp:
            temp_root = Path(temp)
            source_path = temp_root / "input.png"
            source_path.write_bytes(encode_rgba_png(image))
            save_dir = temp_root / "output"
            command = self._command(source_path, save_dir)
            try:
                result = self.runner.run(
                    command,
                    cwd=repo_root,
                    timeout_seconds=self.config.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise ProductionAdapterError(
                    f"See-through inference exceeded {self.config.timeout_seconds:.0f}s timeout"
                ) from exc
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip()[-2000:]
                raise ProductionAdapterError(
                    f"See-through inference failed with exit code {result.returncode}: {tail}"
                )
            optimized = save_dir / "input" / "optimized"
            return self._parse_output(image, optimized)


def decode_source_image(
    payload: bytes,
    *,
    decoder: EncodedImageDecoder | None = None,
) -> SourceImageRgba:
    return (decoder or PillowImageCodec()).decode(payload)
