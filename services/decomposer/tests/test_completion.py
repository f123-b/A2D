from __future__ import annotations

import unittest

from a2d_decomposer import (
    BackendDecompositionV1,
    BackendLayerObservationV1,
    CompletionRequestV1,
    CompletionResponseV1,
    DeterministicReferenceCompletionProvider,
    OcclusionCompletionConfig,
    PixelRect,
    ScriptedReferenceBackend,
    SourceImageRgba,
    complete_occlusions,
    decompose_image,
    refine_decomposer_result,
)
from a2d_decomposer.bridge import decompose_and_compile


def source() -> SourceImageRgba:
    return SourceImageRgba(128, 128, bytes((90, 110, 140, 255)) * (128 * 128))


def part(key, semantic, x, y, w, h, z, *, confidence=1.0, alpha=None, rgba=None):
    return BackendLayerObservationV1(
        key, semantic, PixelRect(x, y, w, h),
        rgba if rgba is not None else bytes((100, 120, 150, 255)) * (w * h),
        alpha if alpha is not None else bytes([255]) * (w * h),
        z, confidence,
    )


def required_layers(*, body=True, cloth=False, face_alpha=None, hair=False):
    items = []
    if body:
        items.append(part("body-src", "body", 24, 58, 80, 62, 0))
    if cloth:
        items.append(part("cloth-src", "cloth", 24, 58, 80, 62, 2, confidence=0.9))
    items.extend([
        part("face-src", "face", 34, 18, 60, 52, 10, alpha=face_alpha),
        part("eye-l-src", "eye_white_l", 43, 36, 18, 10, 20),
        part("eye-r-src", "eye_white_r", 67, 36, 18, 10, 21),
        part("iris-l-src", "iris_l", 49, 38, 8, 8, 30),
        part("iris-r-src", "iris_r", 73, 38, 8, 8, 31),
        part("mouth-src", "mouth", 56, 55, 18, 10, 40),
    ])
    if hair:
        items.append(part("hair-front-src", "hair_front", 38, 18, 52, 18, 50))
    return items


def normalized_refined(layers):
    backend = ScriptedReferenceBackend(BackendDecompositionV1(
        tuple(layers), backend_name="completion-fixture", backend_revision="1"
    ))
    return refine_decomposer_result(decompose_image("complete", source(), backend), source())


def face_with_hole() -> bytes:
    width, height = 60, 52
    alpha = bytearray([255]) * (width * height)
    for y in range(0, 14):
        for x in range(18, 42):
            alpha[y * width + x] = 0
    return bytes(alpha)


class MutatingProvider:
    provider_name = "mutator"
    provider_revision = "1"

    def complete(self, request):
        rgba = bytearray(request.visible_rgba)
        rgba[0] ^= 1
        for i, value in enumerate(request.completion_mask):
            if value:
                rgba[i * 4:i * 4 + 4] = bytes((200, 100, 90, 255))
        return CompletionResponseV1(bytes(rgba), 0.9)


class BadSizeProvider:
    provider_name = "bad-size"
    provider_revision = "1"

    def complete(self, request):
        return CompletionResponseV1(b"\x00" * 4, 0.9)


class CountingProvider(DeterministicReferenceCompletionProvider):
    def __init__(self):
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        return super().complete(request)


class OcclusionCompletionTests(unittest.TestCase):
    def test_reference_provider_preserves_protected_pixels(self):
        image = SourceImageRgba(2, 2, bytes((1, 2, 3, 255)) * 4)
        rgba = bytes((10, 20, 30, 255, 40, 50, 60, 0,
                      70, 80, 90, 255, 100, 110, 120, 255))
        request = CompletionRequestV1(
            "face", "face", (0, 0, 1, 1), 2, 2,
            rgba, bytes((255, 0, 255, 255)), bytes((0, 255, 0, 0)), image,
        )
        response = DeterministicReferenceCompletionProvider().complete(request)
        self.assertEqual(response.rgba[:4], rgba[:4])
        self.assertEqual(response.rgba[8:], rgba[8:])
        self.assertEqual(response.rgba[7], 255)

    def test_face_hole_under_front_hair_is_completed(self):
        refined = normalized_refined(required_layers(face_alpha=face_with_hole(), hair=True))
        old = next(item for item in refined.assets if item.semantic == "face")
        completed = complete_occlusions(refined, source(), DeterministicReferenceCompletionProvider())
        new = next(item for item in completed.assets if item.semantic == "face")
        self.assertGreater(sum(new.alpha), sum(old.alpha))
        self.assertIn("occlusion-completed", {item.code for item in completed.findings})
        self.assertTrue(completed.ready)

    def test_visible_face_pixels_are_byte_identical(self):
        refined = normalized_refined(required_layers(face_alpha=face_with_hole(), hair=True))
        old = next(item for item in refined.assets if item.semantic == "face")
        completed = complete_occlusions(refined, source(), DeterministicReferenceCompletionProvider())
        new = next(item for item in completed.assets if item.semantic == "face")
        for i, alpha in enumerate(old.alpha):
            if alpha:
                self.assertEqual(old.rgba[i * 4:i * 4 + 4], new.rgba[i * 4:i * 4 + 4])

    def test_missing_provider_is_warning_not_blocker(self):
        refined = normalized_refined(required_layers(face_alpha=face_with_hole(), hair=True))
        completed = complete_occlusions(refined, source(), None)
        self.assertTrue(completed.ready)
        self.assertIn("completion-provider-missing", {item.code for item in completed.findings})

    def test_provider_cannot_mutate_protected_pixels(self):
        refined = normalized_refined(required_layers(face_alpha=face_with_hole(), hair=True))
        completed = complete_occlusions(refined, source(), MutatingProvider())
        self.assertFalse(completed.ready)
        self.assertIn("completion-visible-pixel-mutated", {item.code for item in completed.findings})

    def test_bad_provider_output_size_is_blocking(self):
        refined = normalized_refined(required_layers(face_alpha=face_with_hole(), hair=True))
        completed = complete_occlusions(refined, source(), BadSizeProvider())
        self.assertFalse(completed.ready)
        self.assertIn("completion-output-size-invalid", {item.code for item in completed.findings})

    def test_body_proxy_requests_full_completion(self):
        refined = normalized_refined(required_layers(body=False, cloth=True))
        old = next(item for item in refined.assets if item.semantic == "body")
        completed = complete_occlusions(refined, source(), DeterministicReferenceCompletionProvider())
        new = next(item for item in completed.assets if item.semantic == "body")
        self.assertNotEqual(old.rgba, new.rgba)
        self.assertTrue(all(value == 255 for value in new.alpha))
        codes = [item.code for item in completed.findings if item.subject_id == "body"]
        self.assertIn("occlusion-completed", codes)

    def test_reference_completion_is_low_confidence_but_not_blocking(self):
        refined = normalized_refined(required_layers(body=False, cloth=True))
        completed = complete_occlusions(refined, source(), DeterministicReferenceCompletionProvider())
        self.assertTrue(completed.ready)
        self.assertIn("completion-low-confidence", {item.code for item in completed.findings})

    def test_no_occlusion_does_not_call_provider(self):
        refined = normalized_refined(required_layers())
        provider = CountingProvider()
        completed = complete_occlusions(refined, source(), provider)
        self.assertEqual(provider.calls, 0)
        self.assertNotIn("occlusion-completed", {item.code for item in completed.findings})

    def test_completion_is_deterministic_and_changes_revision(self):
        refined = normalized_refined(required_layers(face_alpha=face_with_hole(), hair=True))
        provider = DeterministicReferenceCompletionProvider()
        a = complete_occlusions(refined, source(), provider)
        b = complete_occlusions(refined, source(), provider)
        self.assertEqual(a.package_dict(), b.package_dict())
        self.assertEqual(a.asset_bytes(), b.asset_bytes())
        self.assertEqual(a.source_revision, b.source_revision)
        self.assertNotEqual(a.source_revision, refined.source_revision)

    def test_invalid_config_is_rejected(self):
        refined = normalized_refined(required_layers())
        with self.assertRaisesRegex(ValueError, "min_completion_pixels"):
            complete_occlusions(refined, source(), None,
                                config=OcclusionCompletionConfig(min_completion_pixels=0))

    def test_bridge_runs_completion_before_p2(self):
        backend = ScriptedReferenceBackend(BackendDecompositionV1(
            tuple(required_layers(body=False, cloth=True)),
            backend_name="completion-e2e", backend_revision="1",
        ))
        result = decompose_and_compile(
            "completion-e2e", source(), backend,
            completion_provider=DeterministicReferenceCompletionProvider(),
        )
        self.assertTrue(result.decomposer.ready)
        self.assertIsNotNone(result.compiler)
        self.assertTrue(result.compiler.qa.ready)
        self.assertIsNotNone(result.compiler.artifact)
        self.assertIn("occlusion-completed", {item.code for item in result.decomposer.findings})


if __name__ == "__main__":
    unittest.main()
