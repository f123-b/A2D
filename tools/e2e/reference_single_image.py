from __future__ import annotations

import argparse
from pathlib import Path

from a2d_decomposer.bridge import decompose_and_compile
from a2d_decomposer.contract import (
    BackendDecompositionV1,
    BackendLandmarkObservationV1,
    BackendLayerObservationV1,
    PixelRect,
    SourceImageRgba,
)
from a2d_decomposer.e2e import E2EMode, build_e2e_preflight, write_e2e_preflight_bundle
from a2d_decomposer.pipeline import ScriptedReferenceBackend
from a2d_decomposer.production import encode_rgba_png


def source() -> SourceImageRgba:
    width = height = 128
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend((96 + x // 4, 104 + y // 5, 152, 255))
    return SourceImageRgba(width, height, bytes(pixels))


def part(
    key: str,
    semantic: str,
    x: int,
    y: int,
    width: int,
    height: int,
    z: int,
) -> BackendLayerObservationV1:
    rgba = bytes((115, 135, 170, 255)) * (width * height)
    return BackendLayerObservationV1(
        key,
        semantic,
        PixelRect(x, y, width, height),
        rgba,
        bytes([255]) * (width * height),
        z,
        0.99,
    )


def backend() -> ScriptedReferenceBackend:
    layers = (
        part("hair-back-src", "hair_back", 18, 5, 92, 94, 0),
        part("body-src", "body", 25, 58, 78, 62, 10),
        part("face-src", "face", 35, 18, 58, 52, 20),
        part("brow-l-src", "brow_l", 43, 29, 18, 6, 30),
        part("brow-r-src", "brow_r", 67, 29, 18, 6, 31),
        part("eye-l-src", "eye_white_l", 43, 36, 18, 10, 32),
        part("eye-r-src", "eye_white_r", 67, 36, 18, 10, 33),
        part("iris-l-src", "iris_l", 49, 38, 8, 8, 34),
        part("iris-r-src", "iris_r", 73, 38, 8, 8, 35),
        part("mouth-src", "mouth", 55, 55, 20, 10, 36),
        part("hair-side-l-src", "hair_side_l", 19, 13, 18, 72, 37),
        part("hair-side-r-src", "hair_side_r", 91, 13, 18, 72, 38),
        part("hair-front-src", "hair_front", 28, 7, 72, 29, 39),
    )
    landmarks = (
        BackendLandmarkObservationV1("head_center", 64, 44, 0.99),
        BackendLandmarkObservationV1("nose", 64, 47, 0.99),
        BackendLandmarkObservationV1("neck", 64, 64, 0.99),
        BackendLandmarkObservationV1("left_eye_center", 52, 41, 0.99),
        BackendLandmarkObservationV1("right_eye_center", 76, 41, 0.99),
        BackendLandmarkObservationV1("left_iris_center", 53, 42, 0.99),
        BackendLandmarkObservationV1("right_iris_center", 77, 42, 0.99),
        BackendLandmarkObservationV1("mouth_center", 65, 60, 0.99),
        BackendLandmarkObservationV1("left_brow_center", 52, 32, 0.99),
        BackendLandmarkObservationV1("right_brow_center", 76, 32, 0.99),
        BackendLandmarkObservationV1("hair_front_root", 64, 12, 0.99),
        BackendLandmarkObservationV1("hair_side_l_root", 29, 18, 0.99),
        BackendLandmarkObservationV1("hair_side_r_root", 99, 18, 0.99),
        BackendLandmarkObservationV1("hair_back_root", 64, 10, 0.99),
    )
    return ScriptedReferenceBackend(
        BackendDecompositionV1(
            layers,
            landmarks,
            backend_name="a2d-reference-single-image",
            backend_revision="1",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    image = source()
    result = decompose_and_compile("reference-single-image", image, backend())
    payload = encode_rgba_png(image)
    preflight = build_e2e_preflight(
        "reference-single-image",
        payload,
        result,
        mode=E2EMode.REFERENCE,
        backend_name="a2d-reference-single-image",
        backend_revision="1",
    )
    root = write_e2e_preflight_bundle(Path(args.output), preflight, result)
    if not preflight.compiler_qa_ready:
        raise SystemExit("reference E2E compiler QA is not ready")
    if preflight.quality_decision != "pass":
        raise SystemExit(
            f"reference E2E quality must PASS, got {preflight.quality_decision} "
            f"score={preflight.quality_score}"
        )
    if not (root / "character.a2d").is_file():
        raise SystemExit("reference E2E did not emit character.a2d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
