from __future__ import annotations

import unittest

from a2d_decomposer import (
    BackendDecompositionV1,
    BackendLayerObservationV1,
    PixelRect,
    ScriptedReferenceBackend,
    SemanticRefinementConfig,
    SourceImageRgba,
    decompose_image,
    refine_decomposer_result,
)
from a2d_decomposer.bridge import decompose_and_compile


def source() -> SourceImageRgba:
    return SourceImageRgba(128, 128, bytes((110, 130, 160, 255)) * (128 * 128))


def part(
    key: str,
    semantic: str,
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    confidence: float = 1.0,
    alpha: bytes | None = None,
) -> BackendLayerObservationV1:
    return BackendLayerObservationV1(
        key,
        semantic,
        PixelRect(x, y, w, h),
        bytes((100, 120, 150, 255)) * (w * h),
        alpha if alpha is not None else bytes([255]) * (w * h),
        z,
        confidence,
    )


def base_layers(*, body: bool = True, cloth: bool = False, right_eye: bool = True) -> list[BackendLayerObservationV1]:
    items: list[BackendLayerObservationV1] = []
    if body:
        items.append(part("body-src", "body", 24, 58, 80, 62, 0))
    if cloth:
        items.append(part("cloth-src", "cloth", 24, 58, 80, 62, 2, 0.90))
    items.extend([
        part("face-src", "face", 34, 18, 60, 52, 10),
        part("eye-l-src", "eye_white_l", 43, 36, 18, 10, 20, 0.95),
        part("iris-l-src", "iris_l", 49, 38, 8, 8, 30, 0.92),
        part("mouth-src", "mouth", 56, 55, 18, 10, 40),
    ])
    if right_eye:
        items.extend([
            part("eye-r-src", "eye_white_r", 67, 36, 18, 10, 21, 0.94),
            part("iris-r-src", "iris_r", 73, 38, 8, 8, 31, 0.91),
        ])
    return items


def normalize(layers: list[BackendLayerObservationV1], *, revision: str = "1"):
    backend = ScriptedReferenceBackend(
        BackendDecompositionV1(
            tuple(layers),
            backend_name="refinement-fixture",
            backend_revision=revision,
        )
    )
    return decompose_image("refine", source(), backend)


class SemanticRefinementTests(unittest.TestCase):
    def test_missing_body_is_synthesized_from_cloth_with_penalized_confidence(self) -> None:
        original = normalize(base_layers(body=False, cloth=True))
        refined = refine_decomposer_result(original, source())
        records = {item.semantic: item for item in refined.layers}
        self.assertTrue(refined.ready)
        self.assertIn("body", records)
        self.assertAlmostEqual(records["body"].confidence, 0.90 * 0.62)
        self.assertLess(records["body"].z_order, records["cloth"].z_order)
        self.assertIn("body-proxy-synthesized", {item.code for item in refined.findings})

    def test_existing_body_is_not_replaced(self) -> None:
        original = normalize(base_layers(body=True, cloth=True))
        old = next(item for item in original.layers if item.semantic == "body")
        refined = refine_decomposer_result(original, source())
        new = next(item for item in refined.layers if item.semantic == "body")
        self.assertEqual(new.image_uri, old.image_uri)
        self.assertEqual(new.confidence, old.confidence)
        self.assertNotIn("body-proxy-synthesized", {item.code for item in refined.findings})

    def test_missing_right_eye_and_iris_are_mirrored(self) -> None:
        original = normalize(base_layers(body=True, right_eye=False))
        refined = refine_decomposer_result(original, source())
        records = {item.semantic: item for item in refined.layers}
        assets = {item.semantic: item for item in refined.assets}
        self.assertTrue(refined.ready)
        self.assertIn("eye_white_r", records)
        self.assertIn("iris_r", records)
        self.assertAlmostEqual(
            records["eye_white_r"].confidence,
            records["eye_white_l"].confidence * 0.72,
        )
        self.assertEqual(
            assets["eye_white_r"].rgba[:4],
            assets["eye_white_l"].rgba[(assets["eye_white_l"].width - 1) * 4:
                                         assets["eye_white_l"].width * 4],
        )
        self.assertEqual(
            sum(item.code == "semantic-pair-mirrored" for item in refined.findings),
            2,
        )

    def test_missing_required_pair_with_no_source_is_blocking(self) -> None:
        layers = [item for item in base_layers() if item.semantic_label not in {"eye_white_l", "eye_white_r"}]
        refined = refine_decomposer_result(normalize(layers), source())
        self.assertFalse(refined.ready)
        missing = {
            item.subject_id for item in refined.findings
            if item.code == "required-semantic-missing"
        }
        self.assertEqual(missing, {"eye-white-l", "eye-white-r"})

    def test_side_hair_is_extracted_from_real_hair_pixels(self) -> None:
        layers = base_layers()
        layers.append(part("hair-front-src", "hair_front", 10, 8, 108, 88, 50, 0.88))
        refined = refine_decomposer_result(normalize(layers), source())
        records = {item.semantic: item for item in refined.layers}
        assets = {item.semantic: item for item in refined.assets}
        self.assertIn("hair_side_l", records)
        self.assertIn("hair_side_r", records)
        self.assertGreater(sum(assets["hair_side_l"].alpha), 0)
        self.assertGreater(sum(assets["hair_side_r"].alpha), 0)
        self.assertLess(records["hair_side_l"].confidence, records["hair_front"].confidence)
        self.assertEqual(
            sum(item.code == "side-hair-synthesized" for item in refined.findings),
            2,
        )

    def test_pair_geometry_mismatch_is_warning_not_blocker(self) -> None:
        layers = base_layers()
        layers = [item for item in layers if item.semantic_label != "eye_white_r"]
        layers.append(part("eye-r-odd", "eye_white_r", 70, 50, 6, 4, 21, 0.95))
        refined = refine_decomposer_result(normalize(layers), source())
        self.assertTrue(refined.ready)
        self.assertIn(
            "semantic-pair-geometry-mismatch",
            {item.code for item in refined.findings},
        )

    def test_core_z_conflict_is_repaired_and_reported(self) -> None:
        layers = base_layers(body=True, cloth=True)
        layers = [
            part(item.source_key, item.semantic_label, item.bbox.x, item.bbox.y,
                 item.bbox.width, item.bbox.height,
                 99 if item.semantic_label == "body" else
                 5 if item.semantic_label == "iris_l" else item.z_order,
                 item.confidence, item.alpha)
            for item in layers
        ]
        refined = refine_decomposer_result(normalize(layers), source())
        records = {item.semantic: item for item in refined.layers}
        self.assertLess(records["body"].z_order, records["cloth"].z_order)
        self.assertGreater(records["iris_l"].z_order, records["eye_white_l"].z_order)
        self.assertIn("semantic-z-order-corrected", {item.code for item in refined.findings})

    def test_canonical_parent_graph_is_emitted(self) -> None:
        refined = refine_decomposer_result(normalize(base_layers()), source())
        records = {item.semantic: item for item in refined.layers}
        self.assertEqual(records["face"].parent_id, "body")
        self.assertEqual(records["eye_white_l"].parent_id, "face")
        self.assertEqual(records["iris_l"].parent_id, "eye-white-l")

    def test_refinement_is_deterministic_and_changes_revision(self) -> None:
        layers = base_layers(body=False, cloth=True, right_eye=False)
        a = refine_decomposer_result(normalize(layers), source())
        b = refine_decomposer_result(normalize(list(reversed(layers))), source())
        self.assertEqual(a.package_dict(), b.package_dict())
        self.assertEqual(a.asset_bytes(), b.asset_bytes())
        self.assertEqual(a.source_revision, b.source_revision)
        self.assertNotEqual(a.source_revision, normalize(layers).source_revision)

    def test_one_click_bridge_uses_refinement_before_p2(self) -> None:
        backend = ScriptedReferenceBackend(
            BackendDecompositionV1(
                tuple(base_layers(body=False, cloth=True, right_eye=False)),
                backend_name="refined-e2e",
                backend_revision="1",
            )
        )
        result = decompose_and_compile("refined-e2e", source(), backend)
        self.assertTrue(result.decomposer.ready)
        self.assertIsNotNone(result.compiler)
        self.assertTrue(result.compiler.qa.ready)
        self.assertIsNotNone(result.compiler.artifact)
        semantics = {item.semantic for item in result.decomposer.layers}
        self.assertTrue({"body", "eye_white_r", "iris_r"}.issubset(semantics))

    def test_refinement_can_be_disabled_for_debugging(self) -> None:
        backend = ScriptedReferenceBackend(
            BackendDecompositionV1(
                tuple(base_layers(body=False, cloth=True)),
                backend_name="no-refine",
            )
        )
        result = decompose_and_compile(
            "no-refine", source(), backend, refine_semantics=False
        )
        self.assertIsNotNone(result.compiler)
        self.assertFalse(result.compiler.qa.ready)

    def test_invalid_config_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "mirror_confidence_scale"):
            refine_decomposer_result(
                normalize(base_layers()),
                source(),
                config=SemanticRefinementConfig(mirror_confidence_scale=0),
            )


if __name__ == "__main__":
    unittest.main()
