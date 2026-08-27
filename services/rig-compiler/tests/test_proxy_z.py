import struct
import unittest

from a2d_rig_compiler.adaptive_mesh import AdaptiveMesh, MeshQuality, Point2, Triangle
from a2d_rig_compiler.contract import (
    Landmark,
    NormalizedRect,
    NormalizedRigInput,
    Semantic,
    SemanticLayer,
)
from a2d_rig_compiler.proxy_z import (
    ProxyZConfig,
    Pseudo3DHeadDataV1,
    compile_proxy_z_head,
    pack_proxy_z_buffer,
    project_proxy_z_reference,
)


def value(landmarks=()):
    layers = (
        SemanticLayer("body", Semantic.BODY, "body.png", NormalizedRect(0.25, 0.25, 0.5, 0.7), 0),
        SemanticLayer("hair-back", Semantic.HAIR_BACK, "hairb.png", NormalizedRect(0.27, 0.14, 0.46, 0.42), -1),
        SemanticLayer("face", Semantic.FACE, "face.png", NormalizedRect(0.30, 0.20, 0.40, 0.48), 1),
        SemanticLayer("eye-l", Semantic.EYE_WHITE_L, "eye-l.png", NormalizedRect(0.36, 0.33, 0.10, 0.06), 2),
        SemanticLayer("eye-r", Semantic.EYE_WHITE_R, "eye-r.png", NormalizedRect(0.54, 0.33, 0.10, 0.06), 2),
        SemanticLayer("iris-l", Semantic.IRIS_L, "iris-l.png", NormalizedRect(0.39, 0.345, 0.04, 0.035), 3),
        SemanticLayer("iris-r", Semantic.IRIS_R, "iris-r.png", NormalizedRect(0.57, 0.345, 0.04, 0.035), 3),
        SemanticLayer("mouth", Semantic.MOUTH, "mouth.png", NormalizedRect(0.44, 0.52, 0.12, 0.07), 4),
        SemanticLayer("hair-front", Semantic.HAIR_FRONT, "hair.png", NormalizedRect(0.28, 0.15, 0.44, 0.30), 5),
    )
    return NormalizedRigInput("char", 1024, 1024, layers, tuple(landmarks))


def mesh():
    positions = (
        Point2(0.30, 0.20),
        Point2(0.70, 0.20),
        Point2(0.70, 0.68),
        Point2(0.30, 0.68),
        Point2(0.50, 0.44),
    )
    triangles = (
        Triangle(0, 1, 4),
        Triangle(1, 2, 4),
        Triangle(2, 3, 4),
        Triangle(3, 0, 4),
    )
    quality = MeshQuality(5, 4, 30.0, 0.5, 1.0, 0)
    return AdaptiveMesh(positions, positions, triangles, quality)


class ProxyZTests(unittest.TestCase):
    def test_neutral_projection_is_identity(self):
        data = Pseudo3DHeadDataV1((0.5, 0.44), (0.2, 0.24), 0.11, 1.1, 1, 1)
        for point, proxy_z in (
            (Point2(0.5, 0.44), 1.0),
            (Point2(0.62, 0.37), 0.4),
            (Point2(0.34, 0.55), 0.0),
        ):
            out = project_proxy_z_reference(point.x, point.y, proxy_z, 0, 0, data)
            self.assertEqual(out, (point.x, point.y))

    def test_yaw_pitch_golden(self):
        data = Pseudo3DHeadDataV1((0.5, 0.44), (0.2, 0.24), 0.11, 1.1, 1, 1)
        yaw_pos = project_proxy_z_reference(0.60, 0.44, 0.8, 30, 0, data)
        yaw_neg = project_proxy_z_reference(0.60, 0.44, 0.8, -30, 0, data)
        pitch_pos = project_proxy_z_reference(0.50, 0.52, 0.8, 0, 20, data)
        pitch_neg = project_proxy_z_reference(0.50, 0.52, 0.8, 0, -20, data)
        self.assertAlmostEqual(yaw_pos[0], 0.6401267813, 8)
        self.assertAlmostEqual(yaw_pos[1], 0.44, 10)
        self.assertAlmostEqual(yaw_neg[0], 0.5408841290, 8)
        self.assertAlmostEqual(pitch_pos[0], 0.5, 10)
        self.assertAlmostEqual(pitch_pos[1], 0.4840099547, 8)
        self.assertAlmostEqual(pitch_neg[1], 0.5491972427, 8)

    def test_center_depth_exceeds_boundary(self):
        plan = compile_proxy_z_head(
            value(), mesh(), config=ProxyZConfig(smoothing_iterations=0)
        )
        self.assertGreater(plan.proxy_z[4], 0.95)
        self.assertLess(plan.proxy_z[0], 0.05)

    def test_nose_bias_raises_nearest_vertex(self):
        base = compile_proxy_z_head(
            value(), mesh(), config=ProxyZConfig(smoothing_iterations=0)
        )
        with_nose = compile_proxy_z_head(
            value((Landmark("nose", 0.5, 0.44, 1),)),
            mesh(),
            config=ProxyZConfig(smoothing_iterations=0),
        )
        self.assertGreater(with_nose.proxy_z[4], base.proxy_z[4])
        self.assertFalse(any(f.code == "proxy-z-nose-fallback" for f in with_nose.findings))
        self.assertTrue(any(f.code == "proxy-z-nose-fallback" for f in base.findings))

    def test_eye_landmarks_refine_radius(self):
        landmarks = (
            Landmark("eye_l_center", 0.39, 0.36, 1),
            Landmark("eye_r_center", 0.61, 0.36, 1),
            Landmark("nose", 0.5, 0.44, 1),
        )
        plan = compile_proxy_z_head(value(landmarks), mesh())
        self.assertGreater(plan.data.radius[0], 0.20)
        self.assertLessEqual(plan.data.radius[0], 0.24)

    def test_part_depth_biases_are_emitted(self):
        plan = compile_proxy_z_head(value(), mesh())
        got = [(item.semantic.value, item.bias) for item in plan.part_depth_biases]
        self.assertEqual(got, [("hair_front", 0.18), ("hair_back", -0.20)])

    def test_landmark_order_does_not_change_output(self):
        landmarks = [
            Landmark("nose", 0.5, 0.42, 1),
            Landmark("eye_l_center", 0.4, 0.35, 1),
            Landmark("eye_r_center", 0.6, 0.35, 1),
        ]
        a = compile_proxy_z_head(value(landmarks), mesh())
        b = compile_proxy_z_head(value(reversed(landmarks)), mesh())
        self.assertEqual(a, b)

    def test_pack_proxy_z_is_little_endian_f32(self):
        plan = compile_proxy_z_head(value(), mesh())
        raw = pack_proxy_z_buffer(plan)
        self.assertEqual(len(raw), len(plan.proxy_z) * 4)
        unpacked = struct.unpack("<" + "f" * len(plan.proxy_z), raw)
        for actual, expected in zip(unpacked, plan.proxy_z):
            self.assertAlmostEqual(actual, expected, 6)

    def test_invalid_triangle_is_rejected(self):
        bad = AdaptiveMesh(
            (Point2(0.5, 0.5),) * 3,
            (Point2(0.5, 0.5),) * 3,
            (Triangle(0, 1, 9),),
            MeshQuality(3, 1, 30.0, 0.1, 1.0, 0),
        )
        with self.assertRaisesRegex(ValueError, "triangle index"):
            compile_proxy_z_head(value(), bad)


if __name__ == "__main__":
    unittest.main()
