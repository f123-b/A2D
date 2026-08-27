from __future__ import annotations

import unittest

from a2d_decomposer import (
    BackendDecompositionV1,
    BackendLayerObservationV1,
    PixelRect,
    ScriptedReferenceBackend,
    SourceImageRgba,
)
from a2d_decomposer.bridge import (
    decode_decompose_and_compile,
    decompose_and_compile,
    to_rig_compiler_inputs,
)
from a2d_decomposer.pipeline import decompose_image


def source() -> SourceImageRgba:
    return SourceImageRgba(128, 128, bytes((90, 110, 140, 255)) * (128 * 128))


def part(key: str, semantic: str, x: int, y: int, w: int, h: int, z: int):
    rgba = bytes((100, 120, 150, 255)) * (w * h)
    return BackendLayerObservationV1(
        key,
        semantic,
        PixelRect(x, y, w, h),
        rgba,
        bytes([255]) * (w * h),
        z,
    )


def ready_backend() -> ScriptedReferenceBackend:
    layers = (
        part("body-src", "body", 24, 58, 80, 62, 0),
        part("face-src", "face", 34, 18, 60, 52, 10),
        part("eye-l-src", "eye_white_l", 43, 36, 18, 10, 20),
        part("eye-r-src", "eye_white_r", 67, 36, 18, 10, 21),
        part("iris-l-src", "iris_l", 49, 38, 8, 8, 30),
        part("iris-r-src", "iris_r", 73, 38, 8, 8, 31),
        part("mouth-src", "mouth", 56, 55, 18, 10, 40),
    )
    return ScriptedReferenceBackend(
        BackendDecompositionV1(layers, backend_name="bridge-fixture", backend_revision="1")
    )


class FakeDecoder:
    def decode(self, payload: bytes) -> SourceImageRgba:
        self.payload = payload
        return source()


class BridgeTests(unittest.TestCase):
    def test_normalized_assets_convert_to_p2_abi(self) -> None:
        decomposed = decompose_image("bridge", source(), ready_backend())
        bridged = to_rig_compiler_inputs(decomposed)
        self.assertEqual(bridged.value.character_id, "bridge")
        self.assertEqual(len(bridged.value.layers), 7)
        self.assertEqual(set(bridged.masks), {item.id for item in bridged.value.layers})
        self.assertEqual(set(bridged.images), set(bridged.masks))
        self.assertTrue(all(mask.width >= 2 for mask in bridged.masks.values()))

    def test_p3_to_p2_end_to_end_emits_a2d(self) -> None:
        result = decompose_and_compile("single-image", source(), ready_backend())
        self.assertTrue(result.decomposer.ready)
        self.assertIsNotNone(result.compiler)
        self.assertTrue(result.compiler.qa.ready)
        self.assertIsNotNone(result.compiler.artifact)
        self.assertTrue(result.compiler.artifact.a2d.startswith(b"PK"))
        self.assertEqual(len(result.compiler.artifact.sha256), 64)

    def test_encoded_image_entrypoint_uses_decoder_then_compiles(self) -> None:
        decoder = FakeDecoder()
        result = decode_decompose_and_compile(
            "encoded",
            b"fake-jpeg-payload",
            ready_backend(),
            decoder=decoder,
        )
        self.assertEqual(decoder.payload, b"fake-jpeg-payload")
        self.assertTrue(result.compiler.qa.ready)

    def test_not_ready_decomposition_does_not_enter_p2(self) -> None:
        empty = part("face-src", "face", 20, 20, 20, 20, 0)
        broken = BackendLayerObservationV1(
            empty.source_key,
            empty.semantic_label,
            empty.bbox,
            empty.rgba,
            bytes([0]) * 400,
            empty.z_order,
        )
        backend = ScriptedReferenceBackend(BackendDecompositionV1((broken,)))
        result = decompose_and_compile("broken", source(), backend)
        self.assertFalse(result.decomposer.ready)
        self.assertIsNone(result.compiler)

    def test_bridge_refuses_nonready_result(self) -> None:
        empty = part("face-src", "face", 20, 20, 20, 20, 0)
        broken = BackendLayerObservationV1(
            empty.source_key,
            empty.semantic_label,
            empty.bbox,
            empty.rgba,
            bytes([0]) * 400,
            empty.z_order,
        )
        decomposed = decompose_image(
            "broken",
            source(),
            ScriptedReferenceBackend(BackendDecompositionV1((broken,))),
        )
        with self.assertRaisesRegex(ValueError, "not ready"):
            to_rig_compiler_inputs(decomposed)


if __name__ == "__main__":
    unittest.main()
