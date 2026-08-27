from __future__ import annotations

import unittest

from a2d_decomposer import (
    BackendDecompositionV1,
    BackendLandmarkObservationV1,
    BackendLayerObservationV1,
    LandmarkCandidateV1,
    LandmarkFusionConfig,
    PixelRect,
    ScriptedReferenceBackend,
    ScriptedReferenceLandmarkProvider,
    SourceImageRgba,
    decompose_image,
    fuse_landmarks,
    refine_decomposer_result,
)
from a2d_decomposer.bridge import decompose_and_compile


def source() -> SourceImageRgba:
    return SourceImageRgba(
        128, 128, bytes((112, 132, 162, 255)) * (128 * 128)
    )


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


def layers(*, hair: bool = True) -> list[BackendLayerObservationV1]:
    result = [
        part("body-src", "body", 24, 58, 80, 62, 0),
        part("face-src", "face", 34, 18, 60, 52, 10),
        part("brow-l-src", "brow_l", 43, 29, 18, 6, 18),
        part("brow-r-src", "brow_r", 67, 29, 18, 6, 19),
        part("eye-l-src", "eye_white_l", 43, 36, 18, 10, 20),
        part("eye-r-src", "eye_white_r", 67, 36, 18, 10, 21),
        part("iris-l-src", "iris_l", 49, 38, 8, 8, 30),
        part("iris-r-src", "iris_r", 73, 38, 8, 8, 31),
        part("mouth-src", "mouth", 56, 55, 18, 10, 40),
    ]
    if hair:
        result.extend([
            part("hair-front-src", "hair_front", 28, 8, 72, 30, 50, 0.90),
            part("hair-side-l-src", "hair_side_l", 18, 14, 18, 70, 48, 0.86),
            part("hair-side-r-src", "hair_side_r", 92, 14, 18, 70, 49, 0.85),
            part("hair-back-src", "hair_back", 16, 6, 96, 92, -1, 0.88),
        ])
    return result


def normalized(
    *,
    backend_landmarks: tuple[BackendLandmarkObservationV1, ...] = (),
    reverse: bool = False,
):
    items = layers()
    if reverse:
        items.reverse()
    backend = ScriptedReferenceBackend(
        BackendDecompositionV1(
            tuple(items),
            backend_landmarks,
            backend_name="landmark-fixture",
            backend_revision="1",
        )
    )
    value = decompose_image("landmarks", source(), backend)
    return refine_decomposer_result(value, source())


class RaisingProvider:
    provider_name = "raising"
    provider_revision = "1"

    def infer_landmarks(self, image, result):
        raise RuntimeError("provider exploded")


class LandmarkFusionTests(unittest.TestCase):
    def test_geometry_fills_standard_p2_landmarks(self) -> None:
        fused = fuse_landmarks(normalized(), source())
        ids = {item.id for item in fused.landmarks}
        self.assertTrue({
            "head_center", "nose", "neck",
            "eye_l_center", "eye_r_center",
            "iris_l_center", "iris_r_center",
            "mouth_center", "brow_l_center", "brow_r_center",
            "hair_front_root", "hair_side_l_root",
            "hair_side_r_root", "hair_back_root",
        }.issubset(ids))
        self.assertTrue(fused.ready)

    def test_geometry_confidence_is_conservative_for_nose(self) -> None:
        fused = fuse_landmarks(normalized(), source())
        table = {item.id: item for item in fused.landmarks}
        self.assertGreaterEqual(table["nose"].confidence, 0.5)
        self.assertLess(table["nose"].confidence, 0.65)
        self.assertIn(
            "landmark-low-confidence",
            {item.code for item in fused.findings},
        )

    def test_high_confidence_existing_landmark_is_byte_stable(self) -> None:
        original = normalized(backend_landmarks=(
            BackendLandmarkObservationV1("nose", 51, 47, 0.96),
        ))
        before = next(item for item in original.landmarks if item.id == "nose")
        fused = fuse_landmarks(original, source())
        after = next(item for item in fused.landmarks if item.id == "nose")
        self.assertEqual((after.x, after.y, after.confidence),
                         (before.x, before.y, before.confidence))

    def test_provider_alias_is_canonicalized_and_fused(self) -> None:
        provider = ScriptedReferenceLandmarkProvider((
            LandmarkCandidateV1("left_eye_center", 0.405, 0.322, 0.93),
        ))
        fused = fuse_landmarks(normalized(), source(), provider)
        table = {item.id: item for item in fused.landmarks}
        self.assertIn("eye_l_center", table)
        self.assertGreater(table["eye_l_center"].confidence, 0.80)
        self.assertIn("landmark-fused", {item.code for item in fused.findings})

    def test_large_disagreement_selects_strongest_evidence(self) -> None:
        original = normalized(backend_landmarks=(
            BackendLandmarkObservationV1("left_eye_center", 20, 40, 0.55),
        ))
        provider = ScriptedReferenceLandmarkProvider((
            LandmarkCandidateV1("eye_l_center", 0.80, 0.32, 0.96),
        ))
        fused = fuse_landmarks(original, source(), provider)
        eye = next(item for item in fused.landmarks if item.id == "eye_l_center")
        self.assertAlmostEqual(eye.x, 0.80)
        self.assertLess(eye.confidence, 0.96)
        self.assertIn("landmark-disagreement", {item.code for item in fused.findings})

    def test_duplicate_provider_aliases_are_blocking(self) -> None:
        provider = ScriptedReferenceLandmarkProvider((
            LandmarkCandidateV1("left_eye_center", 0.40, 0.32, 0.90),
            LandmarkCandidateV1("eye_l_center", 0.41, 0.32, 0.91),
        ))
        fused = fuse_landmarks(normalized(), source(), provider)
        self.assertFalse(fused.ready)
        self.assertIn("landmark-provider-error", {item.code for item in fused.findings})

    def test_provider_exception_is_blocking(self) -> None:
        fused = fuse_landmarks(normalized(), source(), RaisingProvider())
        self.assertFalse(fused.ready)
        self.assertIn("landmark-provider-error", {item.code for item in fused.findings})

    def test_unsupported_provider_landmark_is_reported_not_blocking(self) -> None:
        provider = ScriptedReferenceLandmarkProvider((
            LandmarkCandidateV1("anime_magic_point", 0.5, 0.5, 0.99),
        ))
        fused = fuse_landmarks(normalized(), source(), provider)
        self.assertTrue(fused.ready)
        self.assertIn(
            "landmark-provider-unsupported",
            {item.code for item in fused.findings},
        )

    def test_hair_root_uses_top_band_not_bbox_center(self) -> None:
        fused = fuse_landmarks(normalized(), source())
        root = next(item for item in fused.landmarks if item.id == "hair_side_l_root")
        hair = next(item for item in fused.layers if item.semantic == "hair_side_l")
        _, y, _, h = hair.bbox
        self.assertLess(root.y, y + h * 0.30)

    def test_neck_lands_between_face_and_body_geometry(self) -> None:
        fused = fuse_landmarks(normalized(), source())
        neck = next(item for item in fused.landmarks if item.id == "neck")
        face = next(item for item in fused.layers if item.semantic == "face")
        body = next(item for item in fused.layers if item.semantic == "body")
        self.assertGreaterEqual(neck.y, min(face.bbox[1] + face.bbox[3], body.bbox[1]))
        self.assertLessEqual(neck.y, max(face.bbox[1] + face.bbox[3], body.bbox[1]))

    def test_fusion_is_deterministic_and_changes_revision(self) -> None:
        a0 = normalized(reverse=False)
        b0 = normalized(reverse=True)
        a = fuse_landmarks(a0, source())
        b = fuse_landmarks(b0, source())
        self.assertEqual(a.landmarks, b.landmarks)
        self.assertEqual(a.source_revision, b.source_revision)
        self.assertNotEqual(a.source_revision, a0.source_revision)

    def test_bridge_runs_landmark_fusion_before_p2(self) -> None:
        backend = ScriptedReferenceBackend(
            BackendDecompositionV1(
                tuple(layers()),
                backend_name="landmark-e2e",
                backend_revision="1",
            )
        )
        result = decompose_and_compile("landmark-e2e", source(), backend)
        self.assertTrue(result.decomposer.ready)
        self.assertIn("eye_l_center", {item.id for item in result.decomposer.landmarks})
        self.assertIn("neck", {item.id for item in result.decomposer.landmarks})
        self.assertIsNotNone(result.compiler)
        self.assertTrue(result.compiler.qa.ready)
        self.assertIsNotNone(result.compiler.artifact)
        self.assertTrue(result.compiler.artifact.a2d.startswith(b"PK"))

    def test_bridge_landmark_fusion_can_be_disabled(self) -> None:
        backend = ScriptedReferenceBackend(
            BackendDecompositionV1(
                tuple(layers(hair=False)),
                backend_name="landmark-disabled",
                backend_revision="1",
            )
        )
        result = decompose_and_compile(
            "landmark-disabled",
            source(),
            backend,
            fuse_landmarks_enabled=False,
        )
        self.assertEqual(result.decomposer.landmarks, ())
        self.assertIsNotNone(result.compiler)

    def test_invalid_config_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "geometry_weight"):
            fuse_landmarks(
                normalized(),
                source(),
                config=LandmarkFusionConfig(geometry_weight=0),
            )


if __name__ == "__main__":
    unittest.main()
