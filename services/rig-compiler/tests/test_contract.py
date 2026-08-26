import unittest

from a2d_rig_compiler import (
    NormalizedRect,
    NormalizedRigInput,
    R8B_PARAMETER_IDS,
    Semantic,
    SemanticLayer,
    compile_rig_plan,
)


def layer(semantic: Semantic, z: int = 0, confidence: float = 1.0) -> SemanticLayer:
    return SemanticLayer(
        id=semantic.value,
        semantic=semantic,
        image_uri=f"layers/{semantic.value}.png",
        bbox=NormalizedRect(0.1, 0.1, 0.5, 0.5),
        z_order=z,
        confidence=confidence,
    )


class RigCompilerContractTests(unittest.TestCase):
    def standard_input(self) -> NormalizedRigInput:
        ordered = [
            Semantic.BODY, Semantic.CLOTH, Semantic.HAIR_BACK, Semantic.FACE,
            Semantic.BROW_L, Semantic.BROW_R,
            Semantic.EYE_WHITE_L, Semantic.EYE_WHITE_R,
            Semantic.IRIS_L, Semantic.IRIS_R,
            Semantic.MOUTH,
            Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_FRONT,
        ]
        return NormalizedRigInput("golden", 2048, 2048, tuple(layer(value, i) for i, value in enumerate(ordered)))

    def test_standard_input_compiles_to_r8b_semantics(self) -> None:
        plan = compile_rig_plan(self.standard_input())
        self.assertEqual(plan.version, 1)
        self.assertEqual(plan.parameter_ids, R8B_PARAMETER_IDS)
        self.assertEqual(len(plan.parts), 14)
        self.assertEqual(len(plan.physics), 4)
        self.assertEqual([item.id for item in plan.expressions], ["happy", "surprised", "angry"])

        parent = {part.id: part.parent for part in plan.parts}
        self.assertEqual(parent["face"], "body")
        self.assertEqual(parent["iris-l"], "eye-white-l")
        self.assertEqual(parent["iris-r"], "eye-white-r")
        self.assertEqual(parent["hair-front"], "face")

    def test_missing_required_semantic_is_rejected(self) -> None:
        value = self.standard_input()
        layers = tuple(item for item in value.layers if item.semantic is not Semantic.MOUTH)
        with self.assertRaisesRegex(ValueError, "missing required semantic layer: mouth"):
            compile_rig_plan(NormalizedRigInput(value.character_id, value.canvas_width, value.canvas_height, layers))

    def test_duplicate_canonical_semantic_is_rejected(self) -> None:
        value = self.standard_input()
        duplicate = SemanticLayer("face-2", Semantic.FACE, "layers/face-2.png", NormalizedRect(0.1, 0.1, 0.5, 0.5), 50)
        with self.assertRaisesRegex(ValueError, "semantic face appears 2 times"):
            compile_rig_plan(NormalizedRigInput(value.character_id, value.canvas_width, value.canvas_height, value.layers + (duplicate,)))

    def test_low_confidence_is_reported_not_silently_dropped(self) -> None:
        value = self.standard_input()
        layers = tuple(
            layer(item.semantic, item.z_order, 0.5 if item.semantic is Semantic.HAIR_FRONT else 1.0)
            for item in value.layers
        )
        plan = compile_rig_plan(NormalizedRigInput(value.character_id, value.canvas_width, value.canvas_height, layers))
        self.assertTrue(any(f.code == "low-layer-confidence" and f.layer_id == "hair_front" for f in plan.findings))

    def test_bbox_must_remain_normalized(self) -> None:
        bad = SemanticLayer("body", Semantic.BODY, "layers/body.png", NormalizedRect(0.8, 0.2, 0.4, 0.4), 0)
        with self.assertRaisesRegex(ValueError, "bbox must remain inside"):
            compile_rig_plan(NormalizedRigInput("bad", 100, 100, (bad,)))


if __name__ == "__main__":
    unittest.main()
