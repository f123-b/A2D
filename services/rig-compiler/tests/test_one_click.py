from __future__ import annotations

import hashlib
import io
import json
import struct
import unittest
import zipfile

from a2d_rig_compiler import (
    AlphaMask, AtlasConfig, NormalizedRect, NormalizedRigInput, RgbaImage,
    Semantic, SemanticLayer, compile_avatar,
)


def layer(semantic: Semantic, index: int, bbox: NormalizedRect, *, layer_id: str | None = None) -> SemanticLayer:
    identifier = layer_id or f"src-{semantic.value}"
    return SemanticLayer(
        id=identifier, semantic=semantic, image_uri=f"layers/{identifier}.rgba",
        bbox=bbox, z_order=index,
    )


def standard_input(*, with_accessory: bool = False) -> NormalizedRigInput:
    boxes = {
        Semantic.BODY: NormalizedRect(0.20, 0.45, 0.60, 0.50),
        Semantic.CLOTH: NormalizedRect(0.22, 0.50, 0.56, 0.42),
        Semantic.HAIR_BACK: NormalizedRect(0.22, 0.08, 0.56, 0.52),
        Semantic.FACE: NormalizedRect(0.25, 0.10, 0.50, 0.42),
        Semantic.BROW_L: NormalizedRect(0.32, 0.20, 0.14, 0.04),
        Semantic.BROW_R: NormalizedRect(0.54, 0.20, 0.14, 0.04),
        Semantic.EYE_WHITE_L: NormalizedRect(0.32, 0.24, 0.14, 0.08),
        Semantic.EYE_WHITE_R: NormalizedRect(0.54, 0.24, 0.14, 0.08),
        Semantic.IRIS_L: NormalizedRect(0.36, 0.25, 0.05, 0.06),
        Semantic.IRIS_R: NormalizedRect(0.59, 0.25, 0.05, 0.06),
        Semantic.MOUTH: NormalizedRect(0.42, 0.38, 0.16, 0.07),
        Semantic.HAIR_SIDE_L: NormalizedRect(0.20, 0.12, 0.16, 0.50),
        Semantic.HAIR_SIDE_R: NormalizedRect(0.64, 0.12, 0.16, 0.50),
        Semantic.HAIR_FRONT: NormalizedRect(0.25, 0.08, 0.50, 0.28),
    }
    ordered = (
        Semantic.BODY, Semantic.CLOTH, Semantic.HAIR_BACK, Semantic.FACE,
        Semantic.BROW_L, Semantic.BROW_R, Semantic.EYE_WHITE_L, Semantic.EYE_WHITE_R,
        Semantic.IRIS_L, Semantic.IRIS_R, Semantic.MOUTH,
        Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_FRONT,
    )
    layers = [layer(value, index, boxes[value]) for index, value in enumerate(ordered)]
    if with_accessory:
        layers.append(layer(
            Semantic.ACCESSORY, len(layers), NormalizedRect(0.72, 0.16, 0.08, 0.12),
            layer_id="src-accessory-ribbon",
        ))
    return NormalizedRigInput("one-click-golden", 2048, 2048, tuple(layers))


def assets(value: NormalizedRigInput, size: int = 8):
    masks = {}
    images = {}
    for index, item in enumerate(value.layers):
        masks[item.id] = AlphaMask(size, size, (1.0,) * (size * size))
        pixel = bytes(((31 * (index + 1)) % 255, (67 * (index + 1)) % 255, (113 * (index + 1)) % 255, 255))
        images[item.id] = RgbaImage(size, size, pixel * (size * size))
    return masks, images


def decoded_model(result):
    assert result.artifact is not None
    with zipfile.ZipFile(io.BytesIO(result.artifact.a2d), "r") as archive:
        return json.loads(archive.read("model.json"))


class OneClickCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = standard_input()
        cls.masks, cls.images = assets(cls.value)
        cls.result = compile_avatar(cls.value, cls.masks, cls.images)

    def test_ready_pipeline_emits_required_a2d_members(self) -> None:
        result = self.result
        self.assertTrue(result.qa.ready)
        self.assertEqual(result.qa.errors, 0)
        self.assertIsNotNone(result.artifact)
        assert result.artifact is not None
        with zipfile.ZipFile(io.BytesIO(result.artifact.a2d), "r") as archive:
            self.assertEqual(archive.namelist(), [
                "buffers/geometry.bin", "manifest.json", "model.json",
                "qa/report.json", "textures/atlas0.rgba",
            ])
            self.assertEqual(json.loads(archive.read("qa/report.json")), result.qa.to_dict())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["entryBuffers"], ["buffers/geometry.bin"])

    def test_model_uses_one_rgba_atlas_and_valid_material_references(self) -> None:
        model = decoded_model(self.result)
        self.assertEqual(len(model["textures"]), 1)
        texture = model["textures"][0]
        self.assertEqual(texture["id"], "atlas0")
        self.assertEqual(texture["format"], "rgba8")
        self.assertEqual(texture["byteLength"], texture["width"] * texture["height"] * 4)
        self.assertEqual(len(model["parts"]), len(self.value.layers))
        self.assertTrue(all(part["material"]["textureId"] == "atlas0" for part in model["parts"]))

    def test_all_buffer_views_are_aligned_and_morph_ranges_stay_in_global_bounds(self) -> None:
        result = self.result
        assert result.artifact is not None
        model = result.artifact.model
        geometry = result.artifact.geometry
        morph_view = model["deformationBuffers"]["morphInfluences"]["view"]
        self.assertEqual(morph_view["byteOffset"] % 4, 0)
        morph_count = morph_view["count"]
        self.assertGreater(morph_count, 0)
        for part in model["parts"]:
            mesh = part["mesh"]
            for name in ("positions", "uvs", "indices", "proxyZ", "influenceRanges"):
                view = mesh[name]
                self.assertEqual(view["byteOffset"] % 4, 0)
                self.assertLessEqual(view["byteOffset"] + view["byteLength"], len(geometry))
            ranges = mesh["influenceRanges"]
            for index in range(ranges["count"]):
                start, count = struct.unpack_from("<II", geometry, ranges["byteOffset"] + index * 8)
                self.assertLessEqual(count, 8)
                self.assertLessEqual(start + count, morph_count)

    def test_iris_clipping_and_head_proxy_deformer_are_materialized(self) -> None:
        model = decoded_model(self.result)
        parts = {part["id"]: part for part in model["parts"]}
        self.assertEqual(parts["iris-l"]["clip"], {"sources": ["eye-white-l"], "mode": "inside"})
        self.assertEqual(parts["iris-r"]["clip"], {"sources": ["eye-white-r"], "mode": "inside"})
        head = next(item for item in model["deformers"] if item["type"] == "pseudo3d_head")
        self.assertIn("face", head["targets"])
        self.assertIn("hair-front", head["targets"])
        self.assertNotIn("body", head["targets"])
        self.assertGreater(head["data"]["depthScale"], 0)

    def test_package_is_byte_deterministic_for_mapping_order(self) -> None:
        first = self.result
        second = compile_avatar(
            self.value,
            dict(reversed(list(self.masks.items()))),
            dict(reversed(list(self.images.items()))),
        )
        self.assertTrue(second.qa.ready)
        assert first.artifact is not None and second.artifact is not None
        self.assertEqual(first.artifact.a2d, second.artifact.a2d)
        self.assertEqual(first.artifact.sha256, second.artifact.sha256)
        self.assertEqual(first.artifact.sha256, hashlib.sha256(first.artifact.a2d).hexdigest())
        with zipfile.ZipFile(io.BytesIO(first.artifact.a2d), "r") as archive:
            self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_missing_mask_returns_structured_blocker_and_no_artifact(self) -> None:
        masks = dict(self.masks)
        del masks["src-mouth"]
        result = compile_avatar(self.value, masks, self.images)
        self.assertFalse(result.qa.ready)
        self.assertIsNone(result.artifact)
        self.assertIn("compile-mask-missing", [item.code for item in result.qa.findings])

    def test_image_mask_dimension_mismatch_returns_structured_blocker(self) -> None:
        images = dict(self.images)
        original = images["src-face"]
        images["src-face"] = RgbaImage(4, 4, original.pixels[:4 * 4 * 4])
        result = compile_avatar(self.value, self.masks, images)
        self.assertFalse(result.qa.ready)
        self.assertIsNone(result.artifact)
        self.assertIn("compile-mesh-failed", [item.code for item in result.qa.findings])

    def test_atlas_capacity_failure_blocks_packaging_after_qa(self) -> None:
        result = compile_avatar(
            self.value, self.masks, self.images,
            atlas_config=AtlasConfig(padding=2, max_size=16),
        )
        self.assertFalse(result.qa.ready)
        self.assertIsNone(result.artifact)
        self.assertIn("compile-package-failed", [item.code for item in result.qa.findings])
        self.assertTrue(any(
            item.stage.value == "cross_stage" for item in result.qa.findings
            if item.code == "compile-package-failed"
        ))

    def test_accessory_is_preserved_without_entering_semantic_morph_or_physics_maps(self) -> None:
        value = standard_input(with_accessory=True)
        masks, images = assets(value)
        result = compile_avatar(value, masks, images)
        self.assertTrue(result.qa.ready)
        self.assertIsNotNone(result.artifact)
        model = decoded_model(result)
        parts = {part["id"]: part for part in model["parts"]}
        self.assertIn("accessory-src-accessory-ribbon", parts)
        self.assertEqual(parts["accessory-src-accessory-ribbon"]["semantic"], "accessory")
        self.assertIn("accessory-mesh-not-assessed-by-semantic-map", [item.code for item in result.qa.findings])

    def test_runtime_physics_and_expression_payloads_are_present(self) -> None:
        model = decoded_model(self.result)
        physics = {item["id"]: item for item in model["physics"]}
        self.assertEqual(set(physics), {
            "hair-front-sway", "hair-side-l-sway", "hair-side-r-sway", "hair-back-sway",
        })
        self.assertTrue(all(item["nodeCount"] >= 2 for item in physics.values()))
        self.assertTrue(all(item["segmentLength"] > 0 for item in physics.values()))
        self.assertEqual({item["id"] for item in model["expressions"]}, {"happy", "surprised", "angry"})


if __name__ == "__main__":
    unittest.main()
