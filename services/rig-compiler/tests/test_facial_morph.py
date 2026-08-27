from __future__ import annotations

import struct
import unittest

from a2d_rig_compiler import (
    AdaptiveMesh, MeshQuality, MorphCompileConfig, MorphIntent, MorphVertexRange,
    NormalizedRect, NormalizedRigInput, Point2, Semantic, SemanticLayer,
    compile_morph_plan, compile_rig_plan, compile_semantic_morphs, compile_semantic_rig,
    pack_morph_buffers,
)


def mesh(points: list[tuple[float, float]]) -> AdaptiveMesh:
    positions = tuple(Point2(*point) for point in points)
    uvs = tuple(Point2(0.0, 0.0) for _ in positions)
    quality = MeshQuality(len(positions), 0, 180.0, 0.0, 1.0, 0)
    return AdaptiveMesh(positions, uvs, (), quality)


def standard_input() -> NormalizedRigInput:
    boxes = {
        Semantic.BODY: NormalizedRect(.20, .45, .60, .50),
        Semantic.CLOTH: NormalizedRect(.22, .50, .56, .42),
        Semantic.HAIR_BACK: NormalizedRect(.22, .08, .56, .52),
        Semantic.FACE: NormalizedRect(.25, .10, .50, .42),
        Semantic.BROW_L: NormalizedRect(.32, .20, .14, .04),
        Semantic.BROW_R: NormalizedRect(.54, .20, .14, .04),
        Semantic.EYE_WHITE_L: NormalizedRect(.32, .24, .14, .08),
        Semantic.EYE_WHITE_R: NormalizedRect(.54, .24, .14, .08),
        Semantic.IRIS_L: NormalizedRect(.36, .25, .05, .06),
        Semantic.IRIS_R: NormalizedRect(.59, .25, .05, .06),
        Semantic.MOUTH: NormalizedRect(.42, .38, .16, .07),
        Semantic.HAIR_SIDE_L: NormalizedRect(.20, .12, .16, .50),
        Semantic.HAIR_SIDE_R: NormalizedRect(.64, .12, .16, .50),
        Semantic.HAIR_FRONT: NormalizedRect(.25, .08, .50, .28),
    }
    ordered = (
        Semantic.BODY, Semantic.CLOTH, Semantic.HAIR_BACK, Semantic.FACE,
        Semantic.BROW_L, Semantic.BROW_R, Semantic.EYE_WHITE_L, Semantic.EYE_WHITE_R,
        Semantic.IRIS_L, Semantic.IRIS_R, Semantic.MOUTH,
        Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_FRONT,
    )
    layers = tuple(
        SemanticLayer(f"src-{s.value}", s, f"layers/{s.value}.png", boxes[s], i)
        for i, s in enumerate(ordered)
    )
    return NormalizedRigInput("morph-golden", 2048, 2048, layers)


class FacialMorphCompilerTests(unittest.TestCase):
    def test_mouth_uses_canonical_parameter_indices(self) -> None:
        value = standard_input()
        plan = compile_semantic_morphs(
            value, Semantic.MOUTH,
            mesh([(.42,.415),(.46,.390),(.50,.415),(.54,.440),(.58,.415)]),
        )
        indices = {record.intent_id: record.parameter_index for record in plan.records}
        self.assertEqual(indices["mouth-open"], 11)
        self.assertEqual(indices["mouth-form"], 12)
        self.assertEqual(plan.ranges[2].count, 0)

    def test_blink_closed_direction_converges_to_pivot(self) -> None:
        bbox = NormalizedRect(.30,.20,.20,.10)
        intent = MorphIntent("blink","eye-white-l","ParamEyeLOpen",(0.,1.),"eye_close_y",.48,"bbox_height")
        plan = compile_morph_plan(
            "eye-white-l", Semantic.EYE_WHITE_L, bbox,
            mesh([(.31,.25),(.40,.21),(.40,.29),(.49,.25)]),
            (intent,), ("ParamEyeLOpen",),
        )
        by_vertex = {r.vertex_index:r for r in plan.records}
        self.assertGreater(-by_vertex[1].delta_y, 0.0)
        self.assertLess(-by_vertex[2].delta_y, 0.0)
        self.assertNotIn(0, by_vertex)
        self.assertNotIn(3, by_vertex)

    def test_mouth_open_separates_upper_and_lower(self) -> None:
        intent = MorphIntent("open","mouth","ParamMouthOpenY",(0.,1.),"mouth_open_y",.38,"bbox_height")
        plan = compile_morph_plan(
            "mouth", Semantic.MOUTH, NormalizedRect(.40,.40,.20,.10),
            mesh([(.45,.425),(.55,.475)]), (intent,), ("ParamMouthOpenY",),
        )
        self.assertLess(plan.records[0].delta_y, 0.0)
        self.assertGreater(plan.records[1].delta_y, 0.0)

    def test_brow_y_and_angle_compile(self) -> None:
        value = standard_input()
        rig_plan = compile_rig_plan(value)
        semantic_rig = compile_semantic_rig(value, rig_plan)
        plan = compile_semantic_morphs(
            value, Semantic.BROW_L, mesh([(.32,.22),(.39,.22),(.46,.22)]),
            rig_plan, semantic_rig,
        )
        ids = {r.intent_id for r in plan.records}
        self.assertIn("brow-l-y", ids)
        self.assertIn("brow-l-angle", ids)

    def test_body_breath_scales_farther_vertex_more(self) -> None:
        bbox = NormalizedRect(.20,.45,.60,.50)
        intent = MorphIntent("breath","body","ParamBreath",(0.,1.),"body_breath_scale_y",.015,"bbox_height")
        plan = compile_morph_plan(
            "body", Semantic.BODY, bbox, mesh([(.50,.60),(.50,.80)]),
            (intent,), ("ParamBreath",),
        )
        self.assertEqual(len(plan.records), 2)
        self.assertGreater(plan.records[1].delta_y, plan.records[0].delta_y)

    def test_binary_layout_matches_runtime(self) -> None:
        intent = MorphIntent("brow-y","brow-l","ParamBrowLY",(-1.,0.,1.),"brow_translate_y",.20,"bbox_height")
        plan = compile_morph_plan(
            "brow-l", Semantic.BROW_L, NormalizedRect(.30,.20,.20,.05),
            mesh([(.30,.225)]), (intent,), ("ParamBrowLY",),
        )
        packed = pack_morph_buffers(plan)
        self.assertEqual(len(packed.influences), 16)
        self.assertEqual(len(packed.ranges), 8)
        pi, dx, dy, weight = struct.unpack("<Ifff", packed.influences)
        self.assertEqual(pi, 0)
        self.assertAlmostEqual(dx, 0.0, places=7)
        self.assertAlmostEqual(dy, -.01, places=7)
        self.assertAlmostEqual(weight, 1.0, places=7)
        self.assertEqual(struct.unpack("<II", packed.ranges), (0,1))

    def test_intent_order_is_deterministic(self) -> None:
        bbox = NormalizedRect(.40,.40,.20,.10)
        m = mesh([(.45,.425),(.55,.475)])
        a = MorphIntent("form","mouth","B",(-1.,0.,1.),"mouth_form_x",.2,"bbox_width")
        b = MorphIntent("open","mouth","A",(0.,1.),"mouth_open_y",.3,"bbox_height")
        p1 = compile_morph_plan("mouth",Semantic.MOUTH,bbox,m,(a,b),("A","B"))
        p2 = compile_morph_plan("mouth",Semantic.MOUTH,bbox,m,(b,a),("A","B"))
        self.assertEqual(p1, p2)

    def test_eight_influence_limit_is_hard_gate(self) -> None:
        bbox = NormalizedRect(.40,.40,.20,.10)
        intents = (
            MorphIntent("open","mouth","A",(0.,1.),"mouth_open_y",.3,"bbox_height"),
            MorphIntent("form","mouth","B",(-1.,0.,1.),"mouth_form_x",.2,"bbox_width"),
        )
        with self.assertRaisesRegex(ValueError, "limit is 1"):
            compile_morph_plan(
                "mouth", Semantic.MOUTH, bbox, mesh([(.45,.425)]), intents, ("A","B"),
                config=MorphCompileConfig(max_influences_per_vertex=1),
            )

    def test_invalid_parameter_and_operation_are_rejected(self) -> None:
        bbox = NormalizedRect(.40,.40,.20,.10)
        m = mesh([(.45,.425)])
        bad_param = MorphIntent("bad","mouth","Missing",(0.,1.),"mouth_open_y",.3,"bbox_height")
        with self.assertRaisesRegex(ValueError, "unknown parameter"):
            compile_morph_plan("mouth",Semantic.MOUTH,bbox,m,(bad_param,),("Known",))
        bad_op = MorphIntent("bad","mouth","Known",(0.,1.),"unsupported",.3,"bbox_height")
        with self.assertRaisesRegex(ValueError, "unsupported morph operation"):
            compile_morph_plan("mouth",Semantic.MOUTH,bbox,m,(bad_op,),("Known",))

    def test_non_morph_semantic_emits_zero_ranges(self) -> None:
        plan = compile_semantic_morphs(
            standard_input(), Semantic.IRIS_L,
            mesh([(.36,.25),(.385,.28),(.41,.31)]),
        )
        self.assertEqual(plan.records, ())
        self.assertEqual(plan.ranges, (
            MorphVertexRange(0,0), MorphVertexRange(0,0), MorphVertexRange(0,0),
        ))


if __name__ == "__main__":
    unittest.main()
