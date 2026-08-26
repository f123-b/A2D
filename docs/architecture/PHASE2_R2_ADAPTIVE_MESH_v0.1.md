# Phase 2 R2 — Adaptive Mesh Contract v0.1

Status: **IMPLEMENTED REFERENCE BACKEND**

## Purpose

Convert one normalized semantic layer plus its alpha mask into deterministic A2D mesh buffers.

The reference implementation is dependency-free Python. It is the correctness oracle for later NumPy/triangle/Rust acceleration.

## Input

```text
SemanticLayer
├── semantic
├── normalized bbox [0,1]
└── image/mask identity

AlphaMask
├── width
├── height
└── alpha [0,1]

Landmarks[]
└── normalized canvas points
```

The mesh core does not decode PNG/WebP and does not know about WebGL/WebGPU.

Image decoding belongs to adapters. `AlphaMask.from_u8()` is the stable byte-mask bridge.

## Algorithm

```text
alpha threshold
    ↓
exposed boundary edges
    ↓
deterministic farthest-point boundary sampling
    ↓
semantic-density interior sampling
    ↓
landmark preservation
    ↓
deterministic Bowyer-Watson Delaunay
    ↓
alpha centroid/edge filtering
    ↓
degenerate / <2° triangle rejection
    ↓
orphan vertex compaction
    ↓
quality metrics
    ↓
A2D binary packing
```

## Semantic defaults

Reference vertex budgets:

| semantic | budget |
| --- | ---: |
| face | 512 |
| body | 320 |
| cloth | 256 |
| brow | 160 |
| eye white | 192 |
| iris | 128 |
| mouth | 192 |
| front hair | 384 |
| side hair | 320 |
| back hair | 384 |
| accessory | 256 |

Eyes, iris, mouth and brows also receive higher sampling density than body/hair.

All budgets are overrideable through `MeshConfig`.

## Determinism

For equal:
- semantic
- bbox
- alpha mask
- landmark set
- MeshConfig

the reference backend must emit identical:
- positions
- UVs
- triangle indices
- quality metrics

Landmark input ordering must not change output.

## Quality metrics

`MeshQuality` reports:
- vertex count
- triangle count
- minimum triangle angle
- maximum normalized edge length
- estimated alpha coverage
- removed degenerate/poor-angle triangles
- warning findings

`assert_mesh_quality()` is the explicit compiler gate.

Default hard construction filter:
- triangle area >= `1e-8`
- triangle angle >= `2°`

Default QA warnings:
- minimum angle < `5°`
- estimated coverage < `0.70`

## Alpha topology

Triangles are retained only when:
- centroid alpha passes threshold
- all three edge-midpoint alpha samples pass half-threshold

This prevents the basic Delaunay result from freely bridging transparent regions.

The v0.1 reference is not a constrained-Delaunay polygon solver. Complex thin holes can still require the later high-quality backend.

## A2D output

`pack_mesh_buffers()` emits:
- positions: little-endian `vec2<f32>`
- UV: little-endian `vec2<f32>`
- indices: `u16` while vertex count <= 65535, otherwise `u32`

The higher compiler stage is responsible for 4-byte buffer-view alignment when combining parts.

## Performance reference

64×64 elliptical face mask, two semantic landmarks:

```text
vertices:   127
triangles:  209
median:     ~17.5 ms
p95:        ~18.8 ms
```

Environment-specific Python microbenchmark only. It is not a release performance target.

## Next

P2-R3:
- semantic deformer rules
- per-part pivot generation
- eye / mouth / brow morph keyforms
- pseudo-Z head proxy generation
