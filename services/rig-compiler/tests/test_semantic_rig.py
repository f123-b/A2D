from __future__ import annotations

import unittest

from a2d_rig_compiler import (
    Landmark,
    NormalizedRect,
    NormalizedRigInput,
    Semantic,
    SemanticLayer,
    compile_rig_plan,
)
from a2d_rig_compiler.semantic_rig import DeformerKind, Pivot2, compile_semantic_rig


def layer(semantic: Semantic, index: int, bbox: NormalizedRect | None = None) -> SemanticLayer:
    return SemanticLayer(
        id=f"src-{semantic.value}",
        semantic=semantic,
        image_uri=f"layers/{semantic.value}.png",
        bbox=bbox or NormalizedRect(0.1, 0.1, 0.5, 0.5),
        z_order=index,
    )


def standard_input(landmarks: tuple[Landmark, ...] = ()) -> NormalizedRigInput:
    semantics = (
        Semantic.BODY, Semantic.CLOTH, Semantic.HAIR_BACK, Semantic.FACE,
        Semantic.BROW_L, Semantic.BROW_R,
        Semantic.EYE_WHITE_L, Semantic.EYE_WHITE_R,
        Semantic.IRIS_L, Semantic.IRIS_R,
        Semantic.MOUTH, Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_FRONT,
    )
    boxes = {
        Semantic.BODY: NormalizedRect(0.2, 0.45, 0.6, 0.5),
        Semantic.FACE: NormalizedRect(0.25, 0.10, 0.5, 0.42),
        Semantic.EYE_WHITE_L: NormalizedRect(0.32, 0.24, 0.14, 0.08),
        Semantic.EYE_WHITE_R: NormalizedRect(0.54, 0.24, 0.14, 0.08),
        Semantic.IRIS_L: NormalizedRect(0.36, 0.25, 0.05, 0.06),
        Semantic.IRIS_R: NormalizedRect(0.59, 0.25, 0.05, 0.06),
        Semantic.MOUTH: NormalizedRect(0.42, 0.38, 0.16, 0.07),
    }
    return NormalizedRigInput(
        "semantic-golden", 2048, 2048,
        tuple(layer(value, i, boxes.get(value)) for i, value in enumerate(semantics)),
        landmarks,
    )


class SemanticRigTests(unittest.TestCase):
    def test_standard_input_builds_canonical_deformer_tree(self) -> None:
        rig = compile_semantic_rig(standard_input())
        ids = [item.id for item in rig.deformers]
        self.assertEqual(ids[:9], [
            "body-motion", "head-pseudo3d", "eye-l-blink", "eye-r-blink",
            "iris-l-gaze", "iris-r-gaze", "mouth-morph", "brow-l-motion", "brow-r-motion",
        ])
        by_id = {item.id: item for item in rig.deformers}
        self.assertEqual(by_id["head-pseudo3d"].parent_deformer_id, "body-motion")
        self.assertEqual(by_id["iris-l-gaze"].parent_deformer_id, "eye-l-blink")
        self.assertEqual(by_id["hair-back-physics"].parent_deformer_id, "body-motion")
        self.assertEqual(by_id["hair-front-physics"].parent_deformer_id, "head-pseudo3d")
        self.assertEqual(by_id["head-pseudo3d"].kind, DeformerKind.PSEUDO3D_HEAD)

    def test_landmarks_override_bbox_pivots(self) -> None:
        value = standard_input((
            Landmark("neck", 0.51, 0.47),
            Landmark("head_center", 0.49, 0.29),
            Landmark("eye_l_center", 0.39, 0.275),
            Landmark("eye_r_center", 0.61, 0.275),
            Landmark("mouth_center", 0.50, 0.415),
        ))
        rig = compile_semantic_rig(value)
        by_id = {item.id: item for item in rig.deformers}
        self.assertEqual(by_id["body-motion"].pivot, Pivot2(0.51, 0.47))
        self.assertEqual(by_id["head-pseudo3d"].pivot, Pivot2(0.49, 0.29))
        self.assertEqual(by_id["eye-l-blink"].pivot, Pivot2(0.39, 0.275))
        self.assertEqual(by_id["mouth-morph"].pivot, Pivot2(0.50, 0.415))
        self.assertFalse(any(item.code == "pivot-bbox-fallback" for item in rig.findings))

    def test_bbox_fallback_is_deterministic_and_reported(self) -> None:
        value = standard_input()
        a = compile_semantic_rig(value)
        b = compile_semantic_rig(NormalizedRigInput(
            value.character_id, value.canvas_width, value.canvas_height,
            tuple(reversed(value.layers)), tuple(reversed(value.landmarks)),
        ))
        self.assertEqual(a, b)
        codes = [(item.code, item.layer_id) for item in a.findings]
        self.assertIn(("pivot-bbox-fallback", "src-face"), codes)
        self.assertIn(("pivot-bbox-fallback", "src-mouth"), codes)

    def test_eye_and_mouth_bindings_cover_tracking_parameters(self) -> None:
        rig = compile_semantic_rig(standard_input())
        by_id = {item.id: item for item in rig.deformers}
        self.assertEqual(
            [item.parameter_id for item in by_id["iris-l-gaze"].bindings],
            ["ParamEyeBallX", "ParamEyeBallY"],
        )
        self.assertEqual(
            [item.parameter_id for item in by_id["mouth-morph"].bindings],
            ["ParamMouthOpenY", "ParamMouthForm"],
        )
        self.assertEqual(by_id["eye-l-blink"].bindings[0].parameter_id, "ParamEyeLOpen")
        self.assertEqual(by_id["eye-r-blink"].bindings[0].parameter_id, "ParamEyeROpen")

    def test_morph_intents_define_facial_keyform_targets(self) -> None:
        rig = compile_semantic_rig(standard_input())
        intents = {item.id: item for item in rig.morph_intents}
        self.assertEqual(intents["eye-white-l-blink"].key_values, (0.0, 1.0))
        self.assertEqual(intents["mouth-form"].key_values, (-1.0, 0.0, 1.0))
        self.assertEqual(intents["mouth-open"].operation, "mouth_open_y")
        self.assertEqual(intents["brow-l-angle"].amplitude_unit, "degrees")
        self.assertEqual(intents["body-breath"].parameter_id, "ParamBreath")

    def test_optional_hair_layers_prune_physics_deformers(self) -> None:
        value = standard_input()
        keep = tuple(item for item in value.layers if item.semantic not in {
            Semantic.HAIR_FRONT, Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_BACK,
        })
        slim = NormalizedRigInput(value.character_id, value.canvas_width, value.canvas_height, keep)
        rig = compile_semantic_rig(slim)
        self.assertFalse(any(item.id.endswith("-physics") for item in rig.deformers))

    def test_duplicate_landmark_ids_are_rejected(self) -> None:
        value = standard_input((Landmark("neck", 0.5, 0.4), Landmark("neck", 0.51, 0.4)))
        with self.assertRaisesRegex(ValueError, "duplicate landmark id: neck"):
            compile_semantic_rig(value)

    def test_external_rig_plan_character_mismatch_is_rejected(self) -> None:
        value = standard_input()
        plan = compile_rig_plan(value)
        other = NormalizedRigInput("other", value.canvas_width, value.canvas_height, value.layers, value.landmarks)
        with self.assertRaisesRegex(ValueError, "character_id"):
            compile_semantic_rig(other, plan)


if __name__ == "__main__":
    unittest.main()
