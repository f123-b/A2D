from __future__ import annotations

from dataclasses import replace
import unittest

from a2d_rig_compiler import (
    AdaptiveMesh,
    CompileQaConfig,
    MeshQuality,
    NormalizedRect,
    NormalizedRigInput,
    Point2,
    Semantic,
    SemanticLayer,
    Triangle,
    compile_auto_physics,
    compile_proxy_z_head,
    compile_qa_report,
    compile_rig_plan,
    compile_semantic_morphs,
    compile_semantic_rig,
)


def layer(semantic: Semantic, index: int, bbox: NormalizedRect) -> SemanticLayer:
    return SemanticLayer(
        id=f"src-{semantic.value}",
        semantic=semantic,
        image_uri=f"layers/{semantic.value}.png",
        bbox=bbox,
        z_order=index,
    )


def standard_input() -> NormalizedRigInput:
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
        Semantic.BROW_L, Semantic.BROW_R,
        Semantic.EYE_WHITE_L, Semantic.EYE_WHITE_R,
        Semantic.IRIS_L, Semantic.IRIS_R,
        Semantic.MOUTH, Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_FRONT,
    )
    return NormalizedRigInput(
        "qa-golden",
        2048,
        2048,
        tuple(layer(value, index, boxes[value]) for index, value in enumerate(ordered)),
    )


def mesh_for_bbox(bbox: NormalizedRect) -> AdaptiveMesh:
    x0, x1 = bbox.x, bbox.x + bbox.width
    xm = (x0 + x1) * 0.5
    y0, y1 = bbox.y, bbox.y + bbox.height
    positions = (
        Point2(x0, y0), Point2(xm, y0), Point2(x1, y0),
        Point2(x1, y1), Point2(xm, y1), Point2(x0, y1),
    )
    return AdaptiveMesh(
        positions=positions,
        uvs=(
            Point2(0, 0), Point2(0.5, 0), Point2(1, 0),
            Point2(1, 1), Point2(0.5, 1), Point2(0, 1),
        ),
        triangles=(
            Triangle(0, 1, 5), Triangle(1, 4, 5),
            Triangle(1, 2, 4), Triangle(2, 3, 4),
        ),
        quality=MeshQuality(
            vertex_count=6,
            triangle_count=4,
            min_angle_degrees=20.0,
            max_edge=1.0,
            coverage_ratio=1.0,
            degenerate_triangles_removed=0,
        ),
    )


def pipeline():
    value = standard_input()
    meshes = {item.semantic: mesh_for_bbox(item.bbox) for item in value.layers}
    rig_plan = compile_rig_plan(value)
    semantic_rig = compile_semantic_rig(value, rig_plan)
    proxy_z = compile_proxy_z_head(value, meshes[Semantic.FACE], semantic_rig)
    morph_semantics = (
        Semantic.BODY,
        Semantic.EYE_WHITE_L,
        Semantic.EYE_WHITE_R,
        Semantic.MOUTH,
        Semantic.BROW_L,
        Semantic.BROW_R,
    )
    morphs = {
        semantic: compile_semantic_morphs(
            value, semantic, meshes[semantic], rig_plan, semantic_rig,
        )
        for semantic in morph_semantics
    }
    physics = compile_auto_physics(value, meshes, rig_plan, semantic_rig)
    return value, meshes, rig_plan, semantic_rig, proxy_z, morphs, physics


def report_from(items):
    value, meshes, rig_plan, semantic_rig, proxy_z, morphs, physics = items
    return compile_qa_report(
        value, meshes, rig_plan, semantic_rig, proxy_z, morphs, physics,
    )


class CompilerQaTests(unittest.TestCase):
    def test_valid_pipeline_is_ready_with_nonblocking_fallback_warnings(self) -> None:
        report = report_from(pipeline())
        self.assertTrue(report.ready)
        self.assertEqual(report.errors, 0)
        self.assertGreater(report.warnings, 0)
        self.assertEqual(report.score, max(0, 100 - 4 * report.warnings))
        self.assertEqual(len(report.stages), 7)

    def test_missing_required_mesh_blocks_compile(self) -> None:
        items = list(pipeline())
        meshes = dict(items[1])
        del meshes[Semantic.MOUTH]
        items[1] = meshes
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("mesh-missing", [item.code for item in report.findings])

    def test_proxy_z_vertex_count_mismatch_blocks_compile(self) -> None:
        items = list(pipeline())
        items[4] = replace(items[4], proxy_z=items[4].proxy_z[:-1])
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("proxy-z-count-mismatch", [item.code for item in report.findings])

    def test_legal_negative_proxy_z_is_not_rejected(self) -> None:
        items = list(pipeline())
        proxy = items[4]
        items[4] = replace(proxy, proxy_z=(-0.20,) + proxy.proxy_z[1:])
        report = report_from(tuple(items))
        self.assertTrue(report.ready)
        self.assertNotIn("proxy-z-out-of-range", [item.code for item in report.findings])

    def test_morph_range_count_mismatch_blocks_compile(self) -> None:
        items = list(pipeline())
        morphs = dict(items[5])
        mouth = morphs[Semantic.MOUTH]
        morphs[Semantic.MOUTH] = replace(mouth, ranges=mouth.ranges[:-1])
        items[5] = morphs
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("morph-range-count-mismatch", [item.code for item in report.findings])

    def test_empty_required_morph_intent_blocks_compile(self) -> None:
        items = list(pipeline())
        morphs = dict(items[5])
        eye = morphs[Semantic.EYE_WHITE_L]
        morphs[Semantic.EYE_WHITE_L] = replace(
            eye,
            records=(),
            ranges=tuple(replace(item, start=0, count=0) for item in eye.ranges),
        )
        items[5] = morphs
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("morph-intent-empty", [item.code for item in report.findings])

    def test_missing_physics_chain_blocks_compile(self) -> None:
        items = list(pipeline())
        physics = items[6]
        items[6] = replace(physics, chains=physics.chains[:-1])
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("physics-chain-missing", [item.code for item in report.findings])

    def test_character_id_mismatch_is_cross_stage_blocker(self) -> None:
        items = list(pipeline())
        items[6] = replace(items[6], character_id="other")
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        cross = [item for item in report.findings if item.stage.value == "cross_stage"]
        self.assertTrue(any(item.code == "character-id-mismatch" for item in cross))

    def test_out_of_range_triangle_index_blocks_compile(self) -> None:
        items = list(pipeline())
        meshes = dict(items[1])
        mouth = meshes[Semantic.MOUTH]
        meshes[Semantic.MOUTH] = replace(mouth, triangles=(Triangle(0, 1, 99),))
        items[1] = meshes
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("mesh-index-out-of-range", [item.code for item in report.findings])

    def test_missing_proxy_z_blocks_compile(self) -> None:
        items = list(pipeline())
        items[4] = None
        report = report_from(tuple(items))
        self.assertFalse(report.ready)
        self.assertIn("proxy-z-missing", [item.code for item in report.findings])

    def test_report_is_deterministic_and_json_ready(self) -> None:
        items = pipeline()
        first = report_from(items)
        reversed_meshes = dict(reversed(list(items[1].items())))
        reversed_morphs = dict(reversed(list(items[5].items())))
        second = compile_qa_report(
            items[0], reversed_meshes, items[2], items[3], items[4], reversed_morphs, items[6],
        )
        self.assertEqual(first, second)
        payload = first.to_dict()
        self.assertEqual(payload["characterId"], "qa-golden")
        self.assertEqual(payload["ready"], True)
        self.assertEqual([stage["stage"] for stage in payload["stages"]], [
            "contract", "mesh", "semantic_rig", "proxy_z", "morph", "physics", "cross_stage",
        ])

    def test_invalid_qa_config_is_rejected(self) -> None:
        items = pipeline()
        with self.assertRaisesRegex(ValueError, "max_morph_influences_per_vertex"):
            compile_qa_report(
                *items,
                config=CompileQaConfig(max_morph_influences_per_vertex=9),
            )


if __name__ == "__main__":
    unittest.main()
