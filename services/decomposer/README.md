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

`SeeThroughProcessBackend` integrates the public See-through V3 command-line pipeline without parsing PSD files:

```text
SourceImageRgba
  → dependency-free temporary PNG
  → inference/scripts/inference_psd.py
  → optimized/info.json + <tag>.png
  → remove square-padding transform
  → source-pixel BackendLayerObservationV1
  → P3-R1 normalizer
```

The adapter deliberately uses the upstream non-PSD output because `further_extr()` already writes cropped PNG parts and `optimized/info.json` with `xyxy`, `depth_median`, tags and frame size.

Production image decode/read/resize is supplied by `PillowImageCodec`; Pillow is lazy and optional:

```bash
pip install -e 'services/decomposer[production]'
```

See-through itself remains an externally pinned runtime environment; A2D does not vendor PyTorch/CUDA/model weights into the core package.

### P3→P2 bridge

```python
from a2d_decomposer import decode_decompose_and_compile

result = decode_decompose_and_compile(
    "character-id",
    encoded_png_or_jpg,
    see_through_backend,
)

if result.compiler and result.compiler.qa.ready:
    a2d_bytes = result.compiler.artifact.a2d
```

`to_rig_compiler_inputs()` converts normalized assets directly into the existing Phase-2 `NormalizedRigInput`, `AlphaMask`, and `RgbaImage` ABI.

### Current semantic boundary

P3-R2 only maps semantics the upstream model actually resolves reliably. It does **not** fabricate missing `body` or side-hair layers from clothing. A See-through result can therefore be structurally valid at P3 while P2 correctly rejects it for missing required semantics. P3-R3 owns semantic refinement/synthesis.

## Tests

```bash
PYTHONPATH=services/decomposer:services/rig-compiler \
python -m unittest discover -s services/decomposer/tests -v
```

## Next

P3-R3 Semantic Refinement:
- body matte synthesis from compatible upstream parts
- hair front/back → front/side/back classification/refinement
- paired eye/brow consistency
- accessory/clothing conflict resolution
- confidence propagation
- required-semantic completion gate
