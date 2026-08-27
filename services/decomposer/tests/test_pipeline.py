from __future__ import annotations

import unittest

from a2d_decomposer import (
    BackendDecompositionV1, BackendLandmarkObservationV1, BackendLayerObservationV1,
    DecomposerConfig, PixelRect, ScriptedReferenceBackend, SourceImageRgba,
    canonicalize_semantic_label, decompose_image, normalize_backend_output,
)


def rgba(width: int, height: int, alpha: int = 255) -> bytes:
    return bytes([40, 80, 120, alpha] * (width * height))


def image() -> SourceImageRgba:
    return SourceImageRgba(16, 16, rgba(16, 16))


def layer(key: str, semantic: str, bbox: PixelRect, *, z: int = 0, confidence: float = 1.0, alpha: bytes | None = None, parent: str | None = None):
    count = bbox.width * bbox.height
    return BackendLayerObservationV1(
        key, semantic, bbox, rgba(bbox.width, bbox.height),
        alpha if alpha is not None else bytes([255] * count), z, confidence, parent,
    )


class DecomposerPipelineTests(unittest.TestCase):
    def test_source_rgba_length_is_strict(self) -> None:
        with self.assertRaisesRegex(ValueError, "RGBA length"):
            SourceImageRgba(2, 2, b"bad").validate()

    def test_semantic_aliases_normalize_to_p2_vocabulary(self) -> None:
        self.assertEqual(canonicalize_semantic_label("Left Eye"), "eye_white_l")
        self.assertEqual(canonicalize_semantic_label("bangs"), "hair_front")
        self.assertEqual(canonicalize_semantic_label("clothing"), "cloth")

    def test_tight_mask_crops_assets_and_bbox(self) -> None:
        mask = bytes([
            0, 0, 0, 0,
            0, 255, 255, 0,
            0, 255, 255, 0,
            0, 0, 0, 0,
        ])
        result = normalize_backend_output("c", image(), BackendDecompositionV1((layer("face-src", "face", PixelRect(4, 5, 4, 4), alpha=mask),)))
        record = result.layers[0]
        asset = result.assets[0]
        self.assertEqual(record.bbox, (5 / 16, 6 / 16, 2 / 16, 2 / 16))
        self.assertEqual((asset.width, asset.height), (2, 2))
        self.assertEqual(len(asset.rgba), 16)
        self.assertEqual(asset.alpha, bytes([255] * 4))

    def test_mask_is_applied_to_rgba_alpha(self) -> None:
        item = BackendLayerObservationV1("face-src", "face", PixelRect(0, 0, 2, 1), bytes([1,2,3,200, 4,5,6,100]), bytes([255,128]), 0)
        result = normalize_backend_output("c", SourceImageRgba(2, 1, rgba(2, 1)), BackendDecompositionV1((item,)))
        self.assertEqual(result.assets[0].rgba[3], 200)
        self.assertEqual(result.assets[0].rgba[7], 50)

    def test_duplicate_canonical_semantic_is_rejected(self) -> None:
        output = BackendDecompositionV1((
            layer("eye-a", "left_eye", PixelRect(1,1,2,2)),
            layer("eye-b", "eye_white_l", PixelRect(3,1,2,2)),
        ))
        with self.assertRaisesRegex(ValueError, "duplicate canonical semantic eye_white_l"):
            normalize_backend_output("c", image(), output)

    def test_multiple_accessories_get_stable_ids_independent_of_input_order(self) -> None:
        a = layer("hat", "accessory", PixelRect(1,1,2,2), z=8)
        b = layer("pin", "ornament", PixelRect(4,1,2,2), z=4)
        first = normalize_backend_output("c", image(), BackendDecompositionV1((a,b)))
        second = normalize_backend_output("c", image(), BackendDecompositionV1((b,a)))
        self.assertEqual(first.layers, second.layers)
        self.assertEqual([item.id for item in first.layers], ["accessory-001", "accessory-002"])

    def test_unknown_semantic_is_reported_and_not_emitted(self) -> None:
        result = normalize_backend_output("c", image(), BackendDecompositionV1((
            layer("bg", "background", PixelRect(0,0,4,4)),
            layer("face", "face", PixelRect(4,4,4,4)),
        )))
        self.assertEqual([item.semantic for item in result.layers], ["face"])
        self.assertIn("semantic-unsupported", [item.code for item in result.findings])
        self.assertTrue(result.ready)

    def test_empty_mask_is_blocking_finding(self) -> None:
        item = layer("face", "face", PixelRect(0,0,2,2), alpha=bytes(4))
        result = normalize_backend_output("c", image(), BackendDecompositionV1((item,)))
        self.assertFalse(result.ready)
        self.assertEqual(result.layers, ())
        self.assertIn("layer-empty-mask", [finding.code for finding in result.findings])

    def test_parent_source_key_resolves_after_stable_ids(self) -> None:
        face = layer("f", "face", PixelRect(2,2,6,6), z=1)
        eye = layer("e", "left_eye", PixelRect(3,3,2,2), z=2, parent="f")
        result = normalize_backend_output("c", image(), BackendDecompositionV1((eye, face)))
        records = {item.semantic: item for item in result.layers}
        self.assertEqual(records["eye_white_l"].parent_id, "face")

    def test_unknown_parent_is_rejected(self) -> None:
        eye = layer("e", "left_eye", PixelRect(3,3,2,2), parent="missing")
        with self.assertRaisesRegex(ValueError, "parent_source_key"):
            normalize_backend_output("c", image(), BackendDecompositionV1((eye,)))

    def test_parent_cycle_is_rejected(self) -> None:
        face = layer("f", "face", PixelRect(2,2,6,6), parent="e")
        eye = layer("e", "left_eye", PixelRect(3,3,2,2), parent="f")
        with self.assertRaisesRegex(ValueError, "parent graph contains a cycle"):
            normalize_backend_output("c", image(), BackendDecompositionV1((face, eye)))

    def test_landmarks_are_canonical_normalized_and_deterministic(self) -> None:
        landmarks = (
            BackendLandmarkObservationV1("right_eye_center", 12, 4),
            BackendLandmarkObservationV1("left_eye_center", 4, 4),
        )
        first = normalize_backend_output("c", image(), BackendDecompositionV1((layer("face", "face", PixelRect(2,2,10,10)),), landmarks))
        second = normalize_backend_output("c", image(), BackendDecompositionV1((layer("face", "face", PixelRect(2,2,10,10)),), tuple(reversed(landmarks))))
        self.assertEqual(first.landmarks, second.landmarks)
        self.assertEqual([(item.id, item.x, item.y) for item in first.landmarks], [
            ("eye_l_center", 0.25, 0.25), ("eye_r_center", 0.75, 0.25),
        ])

    def test_duplicate_canonical_landmark_is_rejected(self) -> None:
        landmarks = (
            BackendLandmarkObservationV1("left_eye_center", 4, 4),
            BackendLandmarkObservationV1("eye_l_center", 5, 4),
        )
        with self.assertRaisesRegex(ValueError, "duplicate canonical landmark"):
            normalize_backend_output("c", image(), BackendDecompositionV1((layer("face", "face", PixelRect(2,2,10,10)),), landmarks))

    def test_low_confidence_is_explicit_warning(self) -> None:
        result = normalize_backend_output("c", image(), BackendDecompositionV1((
            layer("face", "face", PixelRect(2,2,10,10), confidence=0.4),
        ), (BackendLandmarkObservationV1("nose", 8, 7, 0.4),)), config=DecomposerConfig(low_confidence_threshold=0.65))
        self.assertTrue(result.ready)
        codes = [item.code for item in result.findings]
        self.assertIn("layer-low-confidence", codes)
        self.assertIn("landmark-low-confidence", codes)

    def test_package_dict_matches_normalized_layer_contract_shape(self) -> None:
        result = normalize_backend_output("hero", image(), BackendDecompositionV1((layer("face-src", "face", PixelRect(2,2,10,10)),), backend_name="reference", backend_revision="v1"))
        payload = result.package_dict()
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["characterId"], "hero")
        self.assertEqual(payload["canvas"], {"width": 16, "height": 16})
        self.assertEqual(payload["layers"][0]["imageUri"], "layers/face.rgba")
        self.assertEqual(payload["layers"][0]["maskUri"], "masks/face.a8")
        self.assertTrue(str(payload["sourceRevision"]).startswith("sha256:"))
        self.assertEqual(set(result.asset_bytes()), {"layers/face.rgba", "masks/face.a8"})

    def test_source_revision_changes_with_backend_revision(self) -> None:
        obs = (layer("face", "face", PixelRect(2,2,10,10)),)
        a = normalize_backend_output("c", image(), BackendDecompositionV1(obs, backend_name="x", backend_revision="1"))
        b = normalize_backend_output("c", image(), BackendDecompositionV1(obs, backend_name="x", backend_revision="2"))
        self.assertNotEqual(a.source_revision, b.source_revision)

    def test_decompose_image_uses_backend_protocol(self) -> None:
        expected = BackendDecompositionV1((layer("face", "face", PixelRect(2,2,10,10)),), backend_name="scripted")
        result = decompose_image("c", image(), ScriptedReferenceBackend(expected))
        self.assertEqual(result.layers[0].semantic, "face")


if __name__ == "__main__":
    unittest.main()
