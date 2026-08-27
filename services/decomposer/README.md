# A2D Decomposer

Phase 3 converts one flat source image into the normalized semantic-layer package consumed by the Phase-2 rig compiler.

## Pipeline

```text
PNG / JPG / RGBA
        ↓
Production backend
        ↓
BackendDecompositionV1
        ↓
P3-R1 normalization
        ↓
P3-R3 semantic refinement
        ↓
Normalized layers + RGBA/A8 assets
        ↓
P3→P2 bridge
        ↓
compile_avatar()
        ↓
.a2d
```

## P3-R1 — model-independent normalization

The `DecompositionBackend` protocol isolates model code from downstream A2D stages. The zero-dependency `ScriptedReferenceBackend` remains the correctness oracle.

Normalization guarantees:
- canonical semantic aliases
- unique non-accessory semantics and deterministic multi-accessory IDs
- active-alpha tight crops
- mask × source alpha composition
- normalized `[0,1]` bounds / landmarks
- deterministic package-relative assets
- explicit unsupported / confidence findings
- parent-graph resolution and cycle rejection
- source revision hash

## P3-R2 — production adapter

`SeeThroughProcessBackend` invokes the public See-through V3 command line and consumes its non-PSD `optimized/info.json + <tag>.png` output. Model weights, PyTorch and CUDA remain in an externally pinned See-through runtime.

Production image decode/read/resize is supplied by the lazy optional `PillowImageCodec`:

```bash
pip install -e 'services/decomposer[production]'
```

## P3-R3 — semantic refinement

`refine_decomposer_result()` converts structurally valid model output into the semantic shape required by the Phase-2 release gate.

Rules are intentionally conservative:

- missing `body` may be synthesized only from a real `cloth` matte; the proxy is placed behind cloth and receives a confidence penalty
- if exactly one eye-white, iris or brow side is missing, the existing side can be mirrored around the face center with an explicit confidence penalty
- side hair is extracted only from real front/back hair pixels outside the face core; no synthetic paint/inpainting is performed here
- paired facial geometry/confidence mismatches generate warnings
- core visual z-order conflicts are repaired deterministically and reported
- canonical parent hints are emitted for body/face/eyes/iris/mouth/hair
- every synthesized layer produces an explicit finding
- any required semantic that still cannot be obtained is a blocking `required-semantic-missing` finding

P3-R3 is not occlusion completion. It never hallucinates covered anatomy; that remains P3-R4.

### P3→P2 bridge

The one-click entrypoint refines by default before entering Phase 2:

```python
result = decode_decompose_and_compile(
    "character-id",
    encoded_png_or_jpg,
    see_through_backend,
)

if result.compiler and result.compiler.qa.ready:
    a2d_bytes = result.compiler.artifact.a2d
```

For debugging, semantic refinement can be disabled with `refine_semantics=False`.

## Tests

```bash
PYTHONPATH=services/decomposer:services/rig-compiler \
python -m unittest discover -s services/decomposer/tests -v
```

## Next

P3-R4 Occlusion Completion:
- recover covered face/body/hair pixels
- preserve visible pixels exactly
- deterministic completion masks
- model/provider adapter boundary
- completion confidence and QA
