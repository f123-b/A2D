from __future__ import annotations

import unittest

from a2d_rig_compiler import (
    AdaptiveMesh,
    AutoPhysicsPlanV1,
    MeshQuality,
    NormalizedRect,
    NormalizedRigInput,
    PhysicsCompileConfig,
    Point2,
    Semantic,
    SemanticLayer,
    compile_auto_physics,
    compile_physics_chain,
)


def mesh(points: list[tuple[float, float]]) -> AdaptiveMesh:
    positions = tuple(Point2(x, y) for x, y in points)
    return AdaptiveMesh(
        positions=positions,
        uvs=tuple(Point2(0.0, 0.0) for _ in positions),
        triangles=(),
        quality=MeshQuality(
            vertex_count=len(positions),
            triangle_count=0,
            min_angle_degrees=180.0,
            max_edge=0.0,
            coverage_ratio=1.0,
            degenerate_triangles_removed=0,
        ),
    )


def layer(semantic: Semantic, index: int, bbox: NormalizedRect) -> SemanticLayer:
    return SemanticLayer(
        id=f"src-{semantic.value}",
        semantic=semantic,
        image_uri=f"layers/{semantic.value}.png",
        bbox=bbox,
        z_order=index,
    )


def standard_input(include_hair: bool = True) -> NormalizedRigInput:
    boxes = {
        Semantic.BODY: NormalizedRect(0.20, 0.45, 0.60, 0.50),
        Semantic.FACE: NormalizedRect(0.25, 0.10, 0.50, 0.42),
        Semantic.EYE_WHITE_L: NormalizedRect(0.32, 0.24, 0.14, 0.08),
        Semantic.EYE_WHITE_R: NormalizedRect(0.54, 0.24, 0.14, 0.08),
        Semantic.IRIS_L: NormalizedRect(0.36, 0.25, 0.05, 0.06),
        Semantic.IRIS_R: NormalizedRect(0.59, 0.25, 0.05, 0.06),
        Semantic.MOUTH: NormalizedRect(0.42, 0.38, 0.16, 0.07),
        Semantic.HAIR_FRONT: NormalizedRect(0.25, 0.08, 0.50, 0.28),
        Semantic.HAIR_SIDE_L: NormalizedRect(0.20, 0.12, 0.16, 0.50),
        Semantic.HAIR_SIDE_R: NormalizedRect(0.64, 0.12, 0.16, 0.50),
        Semantic.HAIR_BACK: NormalizedRect(0.22, 0.08, 0.56, 0.52),
    }
    semantics = [
        Semantic.BODY,
        Semantic.FACE,
        Semantic.EYE_WHITE_L,
        Semantic.EYE_WHITE_R,
        Semantic.IRIS_L,
        Semantic.IRIS_R,
        Semantic.MOUTH,
    ]
    if include_hair:
        semantics.extend((
            Semantic.HAIR_FRONT,
            Semantic.HAIR_SIDE_L,
            Semantic.HAIR_SIDE_R,
            Semantic.HAIR_BACK,
        ))
    return NormalizedRigInput(
        "physics-golden",
        2048,
        2048,
        tuple(layer(value, index, boxes[value]) for index, value in enumerate(semantics)),
    )


def standard_meshes() -> dict[Semantic, AdaptiveMesh]:
    return {
        Semantic.HAIR_FRONT: mesh([
            (0.30, 0.11), (0.50, 0.105), (0.70, 0.11),
            (0.33, 0.24), (0.50, 0.30), (0.67, 0.24), (0.50, 0.36),
        ]),
        Semantic.HAIR_SIDE_L: mesh([
            (0.22, 0.16), (0.31, 0.17), (0.23, 0.30),
            (0.29, 0.46), (0.25, 0.62),
        ]),
        Semantic.HAIR_SIDE_R: mesh([
            (0.69, 0.17), (0.78, 0.16), (0.77, 0.30),
            (0.71, 0.46), (0.75, 0.62),
        ]),
        Semantic.HAIR_BACK: mesh([
            (0.28, 0.13), (0.50, 0.12), (0.72, 0.13),
            (0.32, 0.34), (0.50, 0.50), (0.68, 0.34), (0.50, 0.60),
        ]),
    }


class AutoPhysicsCompilerTests(unittest.TestCase):
    def test_standard_hair_builds_four_runtime_chains(self) -> None:
        plan = compile_auto_physics(standard_input(), standard_meshes())
        self.assertIsInstance(plan, AutoPhysicsPlanV1)
        self.assertEqual(
            [chain.semantic for chain in plan.chains],
            [Semantic.HAIR_FRONT, Semantic.HAIR_SIDE_L, Semantic.HAIR_SIDE_R, Semantic.HAIR_BACK],
        )
        self.assertEqual(
            [chain.runtime.output_bindings[0].parameter_id for chain in plan.chains],
            ["ParamHairFrontX", "ParamHairSideLX", "ParamHairSideRX", "ParamHairBackX"],
        )

    def test_standard_geometry_hits_r8b_node_counts(self) -> None:
        plan = compile_auto_physics(standard_input(), standard_meshes())
        self.assertEqual([chain.runtime.node_count for chain in plan.chains], [6, 7, 7, 8])

    def test_segment_length_reaches_mesh_tip(self) -> None:
        plan = compile_auto_physics(standard_input(), standard_meshes())
        for chain in plan.chains:
            span = chain.runtime.segment_length * (chain.runtime.node_count - 1)
            self.assertAlmostEqual(span, chain.effective_length, places=12)

    def test_semantic_presets_make_back_hair_heavier_than_front(self) -> None:
        plan = compile_auto_physics(standard_input(), standard_meshes())
        by_semantic = {chain.semantic: chain for chain in plan.chains}
        front = by_semantic[Semantic.HAIR_FRONT].runtime
        back = by_semantic[Semantic.HAIR_BACK].runtime
        self.assertGreater(back.damping, front.damping)
        self.assertLess(back.stiffness, front.stiffness)
        self.assertGreater(back.gravity.y, front.gravity.y)
        self.assertLess(back.output_bindings[0].gain, front.output_bindings[0].gain)

    def test_bbox_root_source_is_explicit_without_landmarks(self) -> None:
        plan = compile_auto_physics(standard_input(), standard_meshes())
        self.assertTrue(all(chain.root_source == "bbox" for chain in plan.chains))
        front = plan.chains[0]
        self.assertAlmostEqual(front.runtime.root.x, 0.50)
        self.assertAlmostEqual(front.runtime.root.y, 0.08 + 0.28 * 0.08)

    def test_nonvertical_geometry_is_reported_not_silently_rotated(self) -> None:
        value = standard_input()
        meshes = standard_meshes()
        meshes[Semantic.HAIR_FRONT] = mesh([
            (0.25, 0.12), (0.45, 0.125), (0.65, 0.13), (0.75, 0.135),
        ])
        plan = compile_auto_physics(value, meshes)
        self.assertIn("physics-nonvertical-geometry", [finding.code for finding in plan.findings])
        front = plan.chains[0]
        self.assertLess(front.verticality, 0.55)
        self.assertEqual(front.runtime.gravity.x, 0.0)

    def test_missing_optional_hair_layers_produce_no_chains(self) -> None:
        plan = compile_auto_physics(standard_input(include_hair=False), {})
        self.assertEqual(plan.chains, ())
        self.assertEqual(plan.findings, ())

    def test_present_hair_without_mesh_is_rejected(self) -> None:
        meshes = standard_meshes()
        del meshes[Semantic.HAIR_SIDE_R]
        with self.assertRaisesRegex(ValueError, "missing mesh for hair semantic: hair_side_r"):
            compile_auto_physics(standard_input(), meshes)

    def test_runtime_ir_shape_matches_phase1_schema(self) -> None:
        plan = compile_auto_physics(standard_input(), standard_meshes())
        ir = plan.chains[0].runtime.to_avatar_ir()
        self.assertEqual(ir["type"], "spring_chain")
        self.assertEqual(ir["nodeCount"], 6)
        self.assertEqual(ir["outputBindings"][0]["source"], "tip")
        self.assertEqual(ir["outputBindings"][0]["min"], -1.0)
        self.assertEqual(ir["outputBindings"][0]["max"], 1.0)
        self.assertEqual(ir["inputBindings"][0]["parameterId"], "ParamAngleX")
        self.assertGreater(ir["segmentLength"], 0.0)

    def test_compile_is_deterministic_for_mesh_vertex_order(self) -> None:
        value = standard_input()
        a_meshes = standard_meshes()
        b_meshes = {
            semantic: mesh(list(reversed([(p.x, p.y) for p in hair_mesh.positions])))
            for semantic, hair_mesh in a_meshes.items()
        }
        a = compile_auto_physics(value, a_meshes)
        b = compile_auto_physics(value, b_meshes)
        for left, right in zip(a.chains, b.chains, strict=True):
            self.assertEqual(left.semantic, right.semantic)
            self.assertAlmostEqual(left.effective_length, right.effective_length, places=12)
            self.assertAlmostEqual(left.verticality, right.verticality, places=12)
            self.assertEqual(left.runtime.to_avatar_ir(), right.runtime.to_avatar_ir())

    def test_invalid_mesh_and_config_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported physics semantic"):
            compile_physics_chain(
                Semantic.FACE,
                "face",
                "ParamHairFrontX",
                mesh([(0.4, 0.2), (0.5, 0.3)]),
                root=type("Pivot", (), {"x": 0.5, "y": 0.1})(),
            )
        with self.assertRaisesRegex(ValueError, "must extend below"):
            compile_physics_chain(
                Semantic.HAIR_FRONT,
                "hair-front",
                "ParamHairFrontX",
                mesh([(0.4, 0.2), (0.5, 0.2)]),
                root=type("Pivot", (), {"x": 0.5, "y": 0.3})(),
            )
        with self.assertRaisesRegex(ValueError, "verticality_warning_threshold"):
            compile_auto_physics(
                standard_input(),
                standard_meshes(),
                config=PhysicsCompileConfig(verticality_warning_threshold=1.1),
            )


if __name__ == "__main__":
    unittest.main()
