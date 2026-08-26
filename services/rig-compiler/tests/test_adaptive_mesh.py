from __future__ import annotations
import math
import unittest

from a2d_rig_compiler.adaptive_mesh import (
    AlphaMask, MeshConfig, MeshGenerationError, Point2,
    assert_mesh_quality, generate_adaptive_mesh, pack_mesh_buffers
)
from a2d_rig_compiler.contract import Landmark, NormalizedRect, Semantic, SemanticLayer


def full_mask(w=12,h=12):
    return AlphaMask(w,h,tuple([1.0]*(w*h)))


def circle_mask(w=32,h=32):
    values=[]
    for y in range(h):
        for x in range(w):
            u=(x+0.5)/w; v=(y+0.5)/h
            d=math.hypot(u-0.5,v-0.5)
            values.append(1.0 if d <= 0.43 else 0.0)
    return AlphaMask(w,h,tuple(values))


class AdaptiveMeshTests(unittest.TestCase):
    def test_full_mask_generates_bounded_quality_mesh(self):
        bbox=NormalizedRect(0.2,0.3,0.4,0.2)
        mesh=generate_adaptive_mesh(Semantic.FACE,bbox,full_mask())
        self.assertGreater(mesh.quality.vertex_count, 8)
        self.assertGreater(mesh.quality.triangle_count, 8)
        self.assertLessEqual(mesh.quality.vertex_count, 512)
        self.assertGreater(mesh.quality.coverage_ratio, 0.65)
        for p in mesh.positions:
            self.assertGreaterEqual(p.x, bbox.x)
            self.assertLessEqual(p.x, bbox.x+bbox.width)
            self.assertGreaterEqual(p.y, bbox.y)
            self.assertLessEqual(p.y, bbox.y+bbox.height)
        assert_mesh_quality(mesh, min_coverage_ratio=0.55, min_angle_degrees=0.1)

    def test_circle_mesh_is_deterministic(self):
        bbox=NormalizedRect(0.1,0.1,0.8,0.8)
        landmarks=(Landmark("center",0.5,0.5), Landmark("left",0.3,0.5))
        a=generate_adaptive_mesh(Semantic.FACE,bbox,circle_mask(),landmarks)
        b=generate_adaptive_mesh(Semantic.FACE,bbox,circle_mask(),tuple(reversed(landmarks)))
        self.assertEqual(a.positions,b.positions)
        self.assertEqual(a.triangles,b.triangles)
        self.assertGreater(a.quality.coverage_ratio,0.55)

    def test_landmark_is_preserved_when_inside_alpha(self):
        bbox=NormalizedRect(0.2,0.2,0.6,0.6)
        lm=Landmark("mouth-center",0.47,0.61)
        mesh=generate_adaptive_mesh(Semantic.MOUTH,bbox,full_mask(),(lm,))
        self.assertIn(Point2(lm.x,lm.y),mesh.positions)

    def test_vertex_budget_is_honored(self):
        cfg=MeshConfig(target_spacing=0.025,max_vertices=64,max_boundary_points=32)
        mesh=generate_adaptive_mesh(Semantic.EYE_WHITE_L,NormalizedRect(0,0,1,1),full_mask(64,64),config=cfg)
        self.assertLessEqual(mesh.quality.vertex_count,64)
        self.assertGreater(mesh.quality.triangle_count,0)

    def test_empty_mask_is_rejected(self):
        mask=AlphaMask(8,8,tuple([0.0]*64))
        with self.assertRaises(MeshGenerationError):
            generate_adaptive_mesh(Semantic.FACE,NormalizedRect(0,0,1,1),mask)

    def test_binary_packer_matches_a2d_layout(self):
        mesh=generate_adaptive_mesh(Semantic.FACE,NormalizedRect(0,0,1,1),full_mask())
        packed=pack_mesh_buffers(mesh)
        self.assertEqual(len(packed.positions),len(mesh.positions)*8)
        self.assertEqual(len(packed.uvs),len(mesh.positions)*8)
        self.assertEqual(packed.index_component_type,"u16")
        self.assertEqual(len(packed.indices),len(mesh.triangles)*3*2)

    def test_donut_hole_is_not_filled_at_triangle_centers(self):
        w = h = 40
        values = []
        for y in range(h):
            for x in range(w):
                u = (x + 0.5) / w
                v = (y + 0.5) / h
                d = math.hypot(u - 0.5, v - 0.5)
                values.append(1.0 if 0.18 <= d <= 0.44 else 0.0)
        mask = AlphaMask(w, h, tuple(values))
        mesh = generate_adaptive_mesh(
            Semantic.ACCESSORY,
            NormalizedRect(0, 0, 1, 1),
            mask,
        )
        for tri in mesh.triangles:
            a, b, c = (mesh.uvs[tri.a], mesh.uvs[tri.b], mesh.uvs[tri.c])
            center = Point2((a.x+b.x+c.x)/3, (a.y+b.y+c.y)/3)
            self.assertGreaterEqual(mask.sample(center.x, center.y), 0.30)

    def test_semantic_default_budget_is_applied(self):
        mesh = generate_adaptive_mesh(
            Semantic.IRIS_L,
            NormalizedRect(0, 0, 1, 1),
            full_mask(64, 64),
        )
        self.assertLessEqual(mesh.quality.vertex_count, 128)

    def test_layer_wrapper_and_u8_mask_adapter(self):
        raw = bytes([255] * 64)
        mask = AlphaMask.from_u8(8, 8, raw)
        layer = SemanticLayer(
            "face-source", Semantic.FACE, "layers/face.png",
            NormalizedRect(0.15, 0.2, 0.7, 0.6), 3,
        )
        from a2d_rig_compiler.adaptive_mesh import generate_layer_mesh
        mesh = generate_layer_mesh(layer, mask)
        self.assertGreater(mesh.quality.triangle_count, 0)
        self.assertTrue(all(0.15 <= p.x <= 0.85 for p in mesh.positions))


if __name__ == "__main__":
    unittest.main()
