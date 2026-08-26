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
