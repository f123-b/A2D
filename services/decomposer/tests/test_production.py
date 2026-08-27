from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from a2d_decomposer import SourceImageRgba
from a2d_decomposer.production import (
    PillowImageCodec,
    ProcessResultV1,
    ProductionAdapterError,
    SeeThroughConfig,
    SeeThroughProcessBackend,
    encode_rgba_png,
)


def rgba(width: int, height: int, alpha: int = 255) -> SourceImageRgba:
    pixel = bytes((50, 80, 120, alpha))
    return SourceImageRgba(width, height, pixel * (width * height))


class FakeCodec:
    def __init__(self) -> None:
        self.sizes: dict[str, tuple[int, int]] = {}
        self.resize_calls: list[tuple[int, int]] = []

    def read_rgba(self, path: Path) -> SourceImageRgba:
        width, height = self.sizes[path.name]
        return rgba(width, height)

    def crop(self, image: SourceImageRgba, rect) -> SourceImageRgba:
        return rgba(rect.width, rect.height)

    def resize(self, image: SourceImageRgba, width: int, height: int) -> SourceImageRgba:
        self.resize_calls.append((width, height))
        return rgba(width, height)


class FixtureRunner:
    def __init__(self, info: dict, codec: FakeCodec, *, returncode: int = 0) -> None:
        self.info = info
        self.codec = codec
        self.returncode = returncode
        self.argv: tuple[str, ...] | None = None
        self.cwd: Path | None = None
        self.source_signature: bytes | None = None

    def run(self, argv, *, cwd: Path, timeout_seconds: float) -> ProcessResultV1:
        self.argv = tuple(argv)
        self.cwd = cwd
        source = Path(argv[argv.index("--srcp") + 1])
        self.source_signature = source.read_bytes()[:8]
        if self.returncode:
            return ProcessResultV1(self.returncode, "", "synthetic CUDA failure")
        save_dir = Path(argv[argv.index("--save_dir") + 1])
        optimized = save_dir / "input" / "optimized"
        optimized.mkdir(parents=True)
        (optimized / "info.json").write_text(json.dumps(self.info), encoding="utf-8")
        for tag, meta in self.info["parts"].items():
            x0, y0, x1, y1 = meta["xyxy"]
            name = f"{tag}.png"
            (optimized / name).write_bytes(b"fixture")
            self.codec.sizes[name] = (x1 - x0, y1 - y0)
        return ProcessResultV1(0, "ok", "")


def make_repo(root: Path) -> Path:
    script = root / "inference" / "scripts" / "inference_psd.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fixture\n", encoding="utf-8")
    return root


class ProductionAdapterTests(unittest.TestCase):
    def test_dependency_free_png_encoder_is_valid_rgba_png(self) -> None:
        payload = encode_rgba_png(rgba(3, 2))
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn(b"IHDR", payload)
        self.assertIn(b"IDAT", payload)
        self.assertTrue(payload.endswith(b"IEND\xaeB`\x82"))

    def test_official_command_and_optimized_output_are_consumed(self) -> None:
        info = {
            "frame_size": [100, 100],
            "parts": {
                "face": {"xyxy": [20, 10, 80, 70], "depth_median": 0.50},
                "mouth": {"xyxy": [40, 50, 60, 60], "depth_median": 0.40},
                "eyewhite-l": {"xyxy": [28, 30, 43, 40], "depth_median": 0.45},
                "irides-l": {"xyxy": [33, 32, 39, 39], "depth_median": 0.44},
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            codec = FakeCodec()
            runner = FixtureRunner(info, codec)
            repo = make_repo(Path(temp) / "see-through")
            backend = SeeThroughProcessBackend(
                SeeThroughConfig(str(repo), python_executable="python3"),
                runner=runner,
                raster_codec=codec,
            )
            result = backend.decompose(rgba(100, 100))

        self.assertEqual(result.backend_name, "see-through")
        by_semantic = {item.semantic_label: item for item in result.layers}
        self.assertEqual(set(by_semantic), {"face", "mouth", "eye_white_l", "iris_l"})
        self.assertEqual(by_semantic["iris_l"].parent_source_key, "eyewhite-l")
        self.assertEqual(by_semantic["mouth"].parent_source_key, "face")
        self.assertGreater(by_semantic["mouth"].z_order, by_semantic["face"].z_order)
        self.assertEqual(runner.source_signature, b"\x89PNG\r\n\x1a\n")
        self.assertIn("inference/scripts/inference_psd.py", runner.argv)
        self.assertIn("--tblr_split", runner.argv)
        self.assertIn("--disable_progressbar", runner.argv)
        self.assertNotIn("--save_to_psd", runner.argv)

    def test_square_padding_is_removed_and_layer_is_resized_to_source_space(self) -> None:
        info = {
            "frame_size": [128, 128],
            "parts": {
                "face": {"xyxy": [32, 40, 96, 88], "depth_median": 0.5},
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            codec = FakeCodec()
            runner = FixtureRunner(info, codec)
            repo = make_repo(Path(temp) / "see-through")
            backend = SeeThroughProcessBackend(
                SeeThroughConfig(str(repo), resolution=128),
                runner=runner,
                raster_codec=codec,
            )
            result = backend.decompose(rgba(200, 100))
        layer = result.layers[0]
        self.assertGreaterEqual(layer.bbox.x, 49)
        self.assertLessEqual(layer.bbox.x, 51)
        self.assertGreater(layer.bbox.width, 95)
        self.assertTrue(codec.resize_calls)

    def test_invalid_xyxy_is_rejected(self) -> None:
        info = {
            "frame_size": [64, 64],
            "parts": {"face": {"xyxy": [20, 20, 10, 30], "depth_median": 0.5}},
        }
        with tempfile.TemporaryDirectory() as temp:
            codec = FakeCodec()
            runner = FixtureRunner(info, codec)
            repo = make_repo(Path(temp) / "see-through")
            backend = SeeThroughProcessBackend(
                SeeThroughConfig(str(repo)),
                runner=runner,
                raster_codec=codec,
            )
            with self.assertRaisesRegex(ProductionAdapterError, "non-positive extent"):
                backend.decompose(rgba(64, 64))

    def test_nonzero_process_exit_surfaces_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            codec = FakeCodec()
            runner = FixtureRunner({"frame_size": [8, 8], "parts": {}}, codec, returncode=7)
            repo = make_repo(Path(temp) / "see-through")
            backend = SeeThroughProcessBackend(
                SeeThroughConfig(str(repo)),
                runner=runner,
                raster_codec=codec,
            )
            with self.assertRaisesRegex(ProductionAdapterError, "synthetic CUDA failure"):
                backend.decompose(rgba(8, 8))

    def test_missing_upstream_script_is_rejected_before_process_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = SeeThroughProcessBackend(
                SeeThroughConfig(str(Path(temp) / "missing")),
                runner=FixtureRunner({"frame_size": [8, 8], "parts": {}}, FakeCodec()),
                raster_codec=FakeCodec(),
            )
            with self.assertRaisesRegex(ProductionAdapterError, "script not found"):
                backend.decompose(rgba(8, 8))

    def test_pillow_is_a_lazy_optional_dependency(self) -> None:
        PillowImageCodec()


if __name__ == "__main__":
    unittest.main()
