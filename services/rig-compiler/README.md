# A2D Rig Compiler

Phase 2 converts a normalized semantic-layer package into an R8B-equivalent A2D rig.

## Pipeline

```text
normalized semantic layers
        ↓
contract validation
        ↓
landmark normalization
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
expression generation
        ↓
QA
        ↓
Avatar IR + binary buffers + .a2d
```

The compiler must not contain renderer-specific code.

## P2-R1 — Rig Compiler Contract

Freezes:
- normalized semantic vocabulary
- normalized `[0,1]` coordinates
- deterministic canonical part IDs / hierarchy / draw order
- R8B parameter target
- hair physics rules
- expression presets
- explicit QA findings

## P2-R2 — Adaptive Mesh Reference

`a2d_rig_compiler.adaptive_mesh` provides a zero-dependency deterministic reference backend:

```text
AlphaMask
  → boundary extraction
  → farthest-point sampling
  → semantic adaptive sampling
  → landmark preservation
  → Delaunay
  → alpha filtering
  → quality gate
  → A2D mesh buffers
```

The pure-Python backend is the correctness oracle. Accelerated NumPy/triangle/Rust implementations may replace it only if they preserve the compiler contract and quality gates.

Run all dependency-free compiler tests:

```bash
PYTHONPATH=services/rig-compiler \
python -m unittest discover -s services/rig-compiler/tests -v
```

## P2-R3 — Semantic rig

P2-R3 compiles `RigPlanV1` into a topology-independent `SemanticRigPlanV1`:

```text
parts + landmarks
      ↓
pivots
      ↓
deformer tree
      ↓
parameter bindings
      ↓
morph intents
```

It deliberately does not create proxy-Z values or vertex morph deltas; those are P2-R4/P2-R5 responsibilities.

## P2-R4 — Proxy-Z head

P2-R4 compiles the face mesh into a neutral-preserving pseudo-depth profile compatible with the existing Phase-1 `pseudo3d_head` Runtime path.

It emits per-vertex `proxyZ`, `Pseudo3DHeadDataV1`, semantic face-depth features and whole-head part depth metadata.

## P2-R5 — Facial morph compiler

P2-R5 resolves semantic `MorphIntent` rules against actual mesh vertices:

```text
MorphIntent + AdaptiveMesh + semantic pivot
              ↓
      bounded vertex deltas
              ↓
      spatial falloff weights
              ↓
u32 parameterIndex + f32 dx + f32 dy + f32 weight
              ↓
       uvec2 vertex ranges
```

The emitted binary layout is the existing Phase-1 Runtime ABI. No renderer-specific conversion layer is required.

## P2-R6 — Auto physics compiler

P2-R6 resolves optional hair semantics against their actual mesh geometry and P2-R3 root pivots:

```text
Hair Semantic + AdaptiveMesh + Semantic Root
              ↓
       root-to-tip extent
              ↓
      semantic node preset
              ↓
 nodeCount + segmentLength
              ↓
damping / stiffness / gravity / gain
              ↓
Phase-1 SpringChainPhysics-compatible IR
```

Runtime v1 initializes chains vertically. P2-R6 therefore reports non-vertical root-to-tip geometry as an explicit QA warning instead of inventing an unsupported chain-orientation field.
