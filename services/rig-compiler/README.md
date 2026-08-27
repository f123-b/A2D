# A2D Rig Compiler

Phase 2 converts a normalized semantic-layer package into an R8B-equivalent A2D rig.

## Pipeline

```text
normalized semantic layers + RGBA layer pixels + alpha masks
        ↓
contract validation
        ↓
adaptive mesh
        ↓
semantic rig rules
        ↓
proxy-Z / head rig
        ↓
facial morph channels
        ↓
physics generation
        ↓
QA release gate
        ↓
deterministic atlas + aligned buffers
        ↓
Avatar IR + qa/report.json + .a2d
```

The compiler contains no renderer-specific code.

Run all dependency-free compiler tests:

```bash
PYTHONPATH=services/rig-compiler \
python -m unittest discover -s services/rig-compiler/tests -v
```

## P2-R1 — Rig Compiler Contract

Freezes normalized semantic vocabulary, `[0,1]` coordinates, canonical part hierarchy/draw order, the R8B parameter target, physics rules, expressions and explicit QA findings.

## P2-R2 — Adaptive Mesh

`a2d_rig_compiler.adaptive_mesh` is the deterministic zero-dependency correctness backend:

```text
AlphaMask → boundary/features/adaptive samples → Delaunay → alpha filtering → quality gate
```

## P2-R3 — Semantic Rig

Compiles parts + landmarks into pivots, a deformer tree, parameter bindings and topology-independent morph intents.

## P2-R4 — Proxy-Z Head

Compiles the face mesh into neutral-preserving pseudo depth compatible with Phase-1 `pseudo3d_head`, including whole-head semantic depth biases.

## P2-R5 — Facial Morph

Resolves semantic MorphIntent rules into the existing Runtime ABI:

```text
u32 parameterIndex + f32 dx + f32 dy + f32 weight
uvec2 influence range / vertex
```

## P2-R6 — Auto Physics

Resolves hair mesh extent + semantic roots into existing Phase-1 `spring_chain` configurations. Runtime v1 remains vertical-chain based, so non-vertical geometry is reported rather than hidden.

## P2-R7 — Cross-stage QA

`CompileQaReportV1` is the single release gate. `ready` is strict (`errors == 0`); warnings reduce score but do not silently block packaging.

## P2-R8 — One-click Compiler

Public entry point:

```python
result = compile_avatar(normalized_input, masks, rgba_images)
```

Inputs are keyed by semantic layer ID:
- `AlphaMask`: local layer alpha used by P2-R2
- `RgbaImage`: straight-alpha RGBA8 pixels used for final texture assembly

The compiler runs P2-R1..R7, then only when `result.qa.ready` is true:

1. packs every layer into one deterministic power-of-two RGBA8 atlas with replicated gutters;
2. remaps local mesh UVs into atlas texel-center UVs;
3. materializes per-part Proxy-Z and globally indexed morph influence ranges;
4. writes little-endian, 4-byte-aligned `buffers/geometry.bin`;
5. serializes Runtime-compatible physics, expressions and deformer metadata;
6. writes `qa/report.json`;
7. emits a deterministic ZIP-compatible `.a2d` and SHA-256.

Failure policy: stage failures and packaging failures return a structured non-ready QA report and `artifact=None`; no partial publishable package is emitted.
