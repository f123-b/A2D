# A2D Decomposer

Phase 3 converts one flat source image into the normalized semantic-layer package consumed by the Phase-2 rig compiler.

## Pipeline

```text
PNG / JPG / RGBA
        ↓
Production backend
        ↓
P3-R1 normalization
        ↓
P3-R3 semantic refinement
        ↓
P3-R4 occlusion completion
        ↓
P3→P2 bridge
        ↓
compile_avatar()
        ↓
.a2d
```

## P3-R1 — model-independent normalization

The `DecompositionBackend` protocol isolates model code from downstream A2D stages. The zero-dependency `ScriptedReferenceBackend` remains the correctness oracle.

Normalization guarantees canonical semantic aliases, active-alpha tight crops, normalized `[0,1]` geometry, deterministic assets, explicit confidence findings, parent-graph validation and source revision hashing.

## P3-R2 — production adapter

`SeeThroughProcessBackend` integrates the public See-through V3 command-line pipeline through `inference/scripts/inference_psd.py` and consumes non-PSD `optimized/info.json + <tag>.png` output. Model weights, PyTorch and CUDA remain outside A2D.

## P3-R3 — semantic refinement

`refine_decomposer_result()` converts production-model output toward the canonical Phase-2 semantic shape without silently hallucinating unsupported content:

- body proxy only from a real cloth matte, with confidence penalty
- one missing eye/iris/brow side can be mirrored from the detected side
- side hair is extracted only from real front/back hair pixels
- pair geometry/confidence inconsistencies are reported
- core draw-order conflicts are corrected deterministically
- canonical parent hints are emitted
- missing required semantics remain blocking

## P3-R4 — occlusion completion

`CompletionProvider` is the model-independent inpainting boundary. A provider receives:

- full source image
- target semantic + normalized bbox
- visible RGBA/A8
- an explicit completion mask

It returns completed RGBA plus confidence.

The completion gate enforces a strict invariant: **pixels outside the completion mask must remain byte-identical**. A provider that changes known visible pixels is rejected before Phase 2.

Current target masks:

```text
face ← hair_front / hair_side_l / hair_side_r overlap with face alpha holes
body ← cloth overlap with body alpha holes
body proxy from P3-R3 ← full target requires completion
```

No provider is required for structural compilation. When hidden pixels are detected without a provider, P3 emits `completion-provider-missing` as a warning and preserves the refined input. A supplied provider with invalid dimensions, invalid confidence or visible-pixel mutation produces a blocking error.

`DeterministicReferenceCompletionProvider` is a dependency-free correctness oracle. It uses deterministic nearest-visible-pixel propagation and intentionally reports low confidence; it is **not** a production visual inpainting model.

### One-click bridge

```python
result = decode_decompose_and_compile(
    "character-id",
    encoded_png_or_jpg,
    see_through_backend,
    completion_provider=my_inpainting_provider,
)

if result.compiler and result.compiler.qa.ready:
    a2d_bytes = result.compiler.artifact.a2d
```

The default ordering is:

```text
decompose → normalize → refine → complete → P2 compile
```

Debugging can disable refinement or completion independently with `refine_semantics=False` or `complete_hidden=False`.

## Tests

```bash
PYTHONPATH=services/decomposer:services/rig-compiler \
python -m unittest discover -s services/decomposer/tests -v
```

## Next

P3-R5 Landmark Fusion:
- face/eye/iris/mouth/brow landmark providers
- geometry-derived hair roots
- provider confidence fusion
- pair consistency and fallback hierarchy
- canonical normalized landmark output for P2
