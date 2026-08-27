# Phase 2 R8 — One-click Compiler Contract v0.1

## Goal

P2-R8 is the Phase-2 integration boundary. It converts validated normalized semantic layers into a publishable `.a2d` without changing the Phase-1 Runtime ABI.

## Public API

```python
compile_avatar(
    value: NormalizedRigInput,
    masks: Mapping[str, AlphaMask],
    images: Mapping[str, RgbaImage],
) -> OneClickCompileResultV1
```

`masks` and `images` are keyed by `SemanticLayer.id`. `RgbaImage` is straight-alpha RGBA8 and must have exactly `width * height * 4` bytes. Image and mask dimensions for a layer must match.

## Pipeline

```text
NormalizedRigInput + masks + RGBA images
        ↓
P2-R1 RigPlan
        ↓
P2-R2 Adaptive Mesh (all source layers)
        ↓
P2-R3 Semantic Rig
        ↓
P2-R4 Proxy-Z
        ↓
P2-R5 Morph
        ↓
P2-R6 Physics
        ↓
P2-R7 CompileQaReportV1
        ↓ ready only
Atlas + Avatar IR + binary buffers + qa/report.json
        ↓
deterministic .a2d
```

## Release rule

A publishable artifact MUST NOT exist when QA is not ready. Stage exceptions are converted into structured QA blockers. Packaging failures are `cross_stage` blockers and also produce no artifact.

## Texture contract

P2-R8 creates one RGBA8 atlas (`textures/atlas0.rgba`) by default.

- deterministic shelf order: height desc, width desc, layer ID asc
- power-of-two atlas dimensions
- default maximum 4096 x 4096
- default 2-pixel replicated gutter
- local UV endpoints map to atlas texel centers
- straight alpha is preserved; Runtime premultiplication remains a Runtime responsibility

This avoids one-texture-per-layer draw/resource overhead and follows the `.a2d` atlas recommendation.

## Geometry buffer contract

`buffers/geometry.bin` is little-endian and every view begins on a 4-byte boundary.

Per part:
- positions: `f32x2`
- atlas UVs: `f32x2`
- indices: `u16` when possible, otherwise `u32`
- Proxy-Z: `f32`
- influence ranges: `u32x2` (`start`, `count`)

Morph influences are one global table using the existing 16-byte Runtime record:

```text
u32 parameterIndex
f32 deltaX
f32 deltaY
f32 weight
```

Part-local P2-R5 range starts are rebased into this global table. The Runtime v1 maximum of 8 influences per vertex remains enforced by P2-R7.

## Proxy-Z materialization

The face uses the exact P2-R4 output. Other head-linked parts reuse the same ellipsoid profile plus P2-R4 semantic depth bias; non-head parts receive neutral zero proxy depth. The pseudo3D head deformer targets head-linked parts, not body/cloth/accessory parts.

## Deformer serialization

P2-R3 `translation` maps to Avatar IR v1 `warp`, with the original semantic kind and channel metadata retained in `data`. Linear parameter bindings are serialized as `scale` / `bias`. Pseudo3D head metadata is emitted in the exact Phase-1 field shape.

## Package contract

The deterministic ZIP contains:

```text
manifest.json
model.json
buffers/geometry.bin
textures/atlas0.rgba
qa/report.json
```

JSON is canonical (sorted keys, compact separators). ZIP member order, timestamps, mode bits and compression mode are fixed. `CompiledAvatarArtifactV1.sha256` is the SHA-256 of the complete `.a2d` bytes.

## Accessories

Multiple accessory layers are preserved and packaged by source layer ID. They do not enter the semantic-keyed morph/physics maps in v1; P2-R7 reports this as informational, not blocking.
