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

## P2-R1

The first milestone freezes:

- normalized input semantic vocabulary
- normalized coordinates (`[0,1]`)
- deterministic canonical part IDs / hierarchy / draw order
- R8B standard parameter target
- hair physics-rule target
- expression preset target
- explicit QA findings instead of silently dropping uncertain layers

Run the dependency-free contract tests:

```bash
PYTHONPATH=services/rig-compiler \
python -m unittest discover -s services/rig-compiler/tests -v
```
