from __future__ import annotations

import unittest

from a2d_decomposer import (
    BackendDecompositionV1,
    BackendLandmarkObservationV1,
    BackendLayerObservationV1,
    DecomposerFindingV1,
    DecomposerResultV1,
    NormalizedLandmarkV1,
    NormalizedLayerRecordV1,
    PixelRect,
    QualityActionKind,
    QualityDecision,
    QualityDimension,
    QualityScoringConfig,
    ScriptedReferenceBackend,
    SourceImageRgba,
    score_character_quality,
)
from a2d_decomposer.bridge import decompose_and_compile


class FakeQa:
    def __init__(self, ready: bool = True, score: int = 100) -> None:
        self.ready = ready
        self.score = score


class FakeCompiler:
    def __init__(self, ready: bool = True, score: int = 100) -> None:
        self.qa = FakeQa(ready, score)


def record(semantic: str, confidence: float = 0.95, z: int = 0) -> NormalizedLayerRecordV1:
    layer_id = semantic.replace("_", "-")
    return NormalizedLayerRecordV1(
        layer_id,
        semantic,
        f"layers/{layer_id}.rgba",
        f"masks/{layer_id}.a8",
        (0.20, 0.20, 0.40, 0.40),
        z,
        confidence,
        None,
    )


def landmark(landmark_id: str, confidence: float = 0.95) -> NormalizedLandmarkV1:
    return NormalizedLandmarkV1(landmark_id, 0.5, 0.5, confidence)


def quality_result(
    *,
    findings: tuple[DecomposerFindingV1, ...] = (),
    layer_confidence: dict[str, float] | None = None,
    landmark_confidence: dict[str, float] | None = None,
) -> DecomposerResultV1:
    layer_confidence = layer_confidence or {}
    landmark_confidence = landmark_confidence or {}
    semantics = (
        "body", "face", "eye_white_l", "eye_white_r",
        "iris_l", "iris_r", "mouth",
    )
    landmark_ids = (
        "head_center", "nose", "neck", "eye_l_center", "eye_r_center",
        "iris_l_center", "iris_r_center", "mouth_center",
    )
    layers = tuple(
        record(item, layer_confidence.get(item, 0.95), index)
        for index, item in enumerate(semantics)
    )
    landmarks = tuple(
        landmark(item, landmark_confidence.get(item, 0.95))
        for item in landmark_ids
    )
    return DecomposerResultV1(
        1, "quality", "sha256:test", 128, 128,
        layers, landmarks, (), findings,
    )


def dimension(report, dimension: QualityDimension) -> int:
    return next(item.score for item in report.dimensions if item.dimension is dimension)


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
) -> BackendLayerObservationV1:
    return BackendLayerObservationV1(
        key,
        semantic,
        PixelRect(x, y, w, h),
        bytes((100, 120, 150, 255)) * (w * h),
        bytes([255]) * (w * h),
        z,
        0.98,
    )


def e2e_backend() -> ScriptedReferenceBackend:
    layers = (
        part("body-src", "body", 24, 58, 80, 62, 0),
        part("face-src", "face", 34, 18, 60, 52, 10),
        part("eye-l-src", "eye_white_l", 43, 36, 18, 10, 20),
        part("eye-r-src", "eye_white_r", 67, 36, 18, 10, 21),
        part("iris-l-src", "iris_l", 49, 38, 8, 8, 30),
        part("iris-r-src", "iris_r", 73, 38, 8, 8, 31),
        part("mouth-src", "mouth", 56, 55, 18, 10, 40),
    )
    landmarks = (
        BackendLandmarkObservationV1("head_center", 64, 44, 0.97),
        BackendLandmarkObservationV1("nose", 64, 45, 0.97),
        BackendLandmarkObservationV1("neck", 64, 64, 0.96),
        BackendLandmarkObservationV1("left_eye_center", 52, 41, 0.97),
        BackendLandmarkObservationV1("right_eye_center", 76, 41, 0.97),
        BackendLandmarkObservationV1("left_iris_center", 53, 42, 0.97),
        BackendLandmarkObservationV1("right_iris_center", 77, 42, 0.97),
        BackendLandmarkObservationV1("mouth_center", 65, 60, 0.96),
    )
    return ScriptedReferenceBackend(BackendDecompositionV1(
        layers,
        landmarks,
        backend_name="quality-e2e",
        backend_revision="1",
    ))


class QualityScoringTests(unittest.TestCase):
    def test_clean_high_confidence_result_passes(self) -> None:
        report = score_character_quality(quality_result(), FakeCompiler())
        self.assertEqual(report.decision, QualityDecision.PASS)
        self.assertTrue(report.ready_for_export)
        self.assertGreaterEqual(report.score, 85)
        self.assertEqual(sum(item.weight for item in report.dimensions), 100)

    def test_missing_completion_provider_requests_retry(self) -> None:
        result = quality_result(findings=(
            DecomposerFindingV1(
                "info", "occlusion-completion-required", "face needs fill", "face"
            ),
            DecomposerFindingV1(
                "warning", "completion-provider-missing", "no provider", "face"
            ),
        ))
        report = score_character_quality(result, FakeCompiler())
        self.assertEqual(report.decision, QualityDecision.RETRY)
        self.assertEqual(dimension(report, QualityDimension.COMPLETION), 35)
        self.assertIn(QualityActionKind.RUN_COMPLETION, {item.kind for item in report.actions})

    def test_low_confidence_completion_requests_retry(self) -> None:
        result = quality_result(findings=(
            DecomposerFindingV1(
                "info", "occlusion-completion-required", "face needs fill", "face"
            ),
            DecomposerFindingV1(
                "info", "occlusion-completed", "face filled", "face"
            ),
            DecomposerFindingV1(
                "warning", "completion-low-confidence", "weak fill", "face"
            ),
        ))
        report = score_character_quality(result, FakeCompiler())
        self.assertEqual(report.decision, QualityDecision.RETRY)
        self.assertEqual(dimension(report, QualityDimension.COMPLETION), 55)

    def test_pair_geometry_mismatch_requires_manual_review(self) -> None:
        result = quality_result(findings=(
            DecomposerFindingV1(
                "warning", "semantic-pair-geometry-mismatch", "eye pair mismatch", "eyes"
            ),
        ))
        report = score_character_quality(result, FakeCompiler())
        self.assertEqual(report.decision, QualityDecision.MANUAL_REVIEW)
        self.assertEqual(dimension(report, QualityDimension.CONSISTENCY), 80)
        self.assertIn(QualityActionKind.REVIEW_SEMANTICS, {item.kind for item in report.actions})

    def test_mirrored_semantic_requires_manual_review(self) -> None:
        result = quality_result(findings=(
            DecomposerFindingV1(
                "warning", "semantic-pair-mirrored", "right eye mirrored", "eye-white-r"
            ),
        ))
        report = score_character_quality(result, FakeCompiler())
        self.assertEqual(report.decision, QualityDecision.MANUAL_REVIEW)
        self.assertEqual(dimension(report, QualityDimension.SYNTHETIC), 88)

    def test_low_confidence_landmark_requests_provider_retry(self) -> None:
        result = quality_result(landmark_confidence={"nose": 0.52})
        report = score_character_quality(result, FakeCompiler())
        self.assertEqual(report.decision, QualityDecision.RETRY)
        self.assertIn(
            QualityActionKind.RUN_LANDMARK_PROVIDER,
            {item.kind for item in report.actions},
        )

    def test_low_ready_compiler_score_requires_manual_review(self) -> None:
        report = score_character_quality(quality_result(), FakeCompiler(True, 60))
        self.assertEqual(report.decision, QualityDecision.MANUAL_REVIEW)
        self.assertEqual(dimension(report, QualityDimension.COMPILER), 60)
        self.assertIn(QualityActionKind.REVIEW_COMPILER, {item.kind for item in report.actions})

    def test_compiler_block_is_hard_block(self) -> None:
        report = score_character_quality(quality_result(), FakeCompiler(False, 20))
        self.assertEqual(report.decision, QualityDecision.BLOCK)
        self.assertFalse(report.ready_for_export)
        self.assertIn("quality-compiler-qa-blocked", {item.code for item in report.findings})

    def test_source_error_is_hard_block(self) -> None:
        result = quality_result(findings=(
            DecomposerFindingV1(
                "error", "required-semantic-missing", "body missing", "body"
            ),
        ))
        report = score_character_quality(result, None)
        self.assertEqual(report.decision, QualityDecision.BLOCK)
        self.assertGreater(report.errors, 0)
        self.assertIn("source-required-semantic-missing", {item.code for item in report.findings})

    def test_missing_compiler_for_ready_p3_is_blocking(self) -> None:
        report = score_character_quality(quality_result(), None)
        self.assertEqual(report.decision, QualityDecision.BLOCK)
        self.assertIn("quality-compiler-missing", {item.code for item in report.findings})

    def test_completed_body_proxy_has_lower_synthetic_penalty(self) -> None:
        base = DecomposerFindingV1(
            "warning", "body-proxy-synthesized", "body proxy", "body"
        )
        unresolved = score_character_quality(
            quality_result(findings=(base,)), FakeCompiler()
        )
        completed = score_character_quality(
            quality_result(findings=(
                base,
                DecomposerFindingV1(
                    "info", "occlusion-completion-required", "body fill", "body"
                ),
                DecomposerFindingV1(
                    "info", "occlusion-completed", "body filled", "body"
                ),
            )),
            FakeCompiler(),
        )
        self.assertGreater(
            dimension(completed, QualityDimension.SYNTHETIC),
            dimension(unresolved, QualityDimension.SYNTHETIC),
        )

    def test_report_is_deterministic_and_serializable(self) -> None:
        result = quality_result(findings=(
            DecomposerFindingV1(
                "warning", "semantic-z-order-corrected", "fixed order", "body"
            ),
        ))
        a = score_character_quality(result, FakeCompiler())
        b = score_character_quality(result, FakeCompiler())
        self.assertEqual(a, b)
        payload = a.to_dict()
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["characterId"], "quality")
        self.assertEqual(len(payload["dimensions"]), 6)

    def test_invalid_weight_sum_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "weights must sum to 100"):
            score_character_quality(
                quality_result(),
                FakeCompiler(),
                config=QualityScoringConfig(compiler_weight=14),
            )

    def test_bridge_emits_quality_report_without_deleting_preview_artifact(self) -> None:
        result = decompose_and_compile("quality-e2e", source(), e2e_backend())
        self.assertTrue(result.decomposer.ready)
        self.assertIsNotNone(result.compiler)
        self.assertTrue(result.compiler.qa.ready)
        self.assertIsNotNone(result.compiler.artifact)
        self.assertIsNotNone(result.quality)
        self.assertNotEqual(result.quality.decision, QualityDecision.BLOCK)
        self.assertTrue(result.compiler.artifact.a2d.startswith(b"PK"))

    def test_bridge_quality_scoring_can_be_disabled(self) -> None:
        result = decompose_and_compile(
            "quality-off",
            source(),
            e2e_backend(),
            quality_scoring_enabled=False,
        )
        self.assertIsNone(result.quality)
        self.assertIsNotNone(result.compiler)


if __name__ == "__main__":
    unittest.main()
