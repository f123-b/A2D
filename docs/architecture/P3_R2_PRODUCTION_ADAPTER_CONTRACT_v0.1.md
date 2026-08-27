# P3-R2 Production Decomposition Adapter Contract v0.1

## Goal

Connect a real single-image decomposition runtime to the stable P3-R1 normalization boundary without leaking upstream model types or filesystem conventions into Phase 2.

## Upstream reference

The first production backend targets See-through V3 through its public command line:

```text
inference/scripts/inference_psd.py
```

A2D invokes non-PSD mode and consumes:

```text
<save_dir>/<source-name>/optimized/
├── info.json
└── <part-tag>.png
```

`info.json` is the authoritative geometry/order sidecar. The adapter does not scrape stdout and does not require PSD parsing.

## Process contract

The adapter:
1. validates `SourceImageRgba`;
2. writes a deterministic RGBA8 PNG;
3. runs See-through from its repository root;
4. passes explicit seed/resolution/checkpoint IDs;
5. enables `--tblr_split` by default;
6. enforces a process timeout;
7. converts non-zero exit into `ProductionAdapterError` with bounded stderr context;
8. parses only after successful process completion.

Model weights and CUDA dependencies remain external to A2D.

## Canvas transform

See-through uses a square, center-padded inference canvas. Output `xyxy` and PNG crops are converted back to original source pixel coordinates before entering P3-R1.

For a source `Ws × Hs` and square model canvas `M × M`:

```text
side = max(Ws, Hs)
scale = M / side
contentWidth  = Ws * scale
contentHeight = Hs * scale
padX = (M - contentWidth) / 2
padY = (M - contentHeight) / 2
```

Part rectangles are intersected with the content area, padding is removed, and layer rasters are resized to the resulting source-pixel rectangle.

## Layer order

See-through's optimized metadata exposes `depth_median`. Smaller values represent more front-facing parts. A2D sorts depth descending and assigns increasing `z_order`, producing back-to-front draw order.

## Semantic mapping

P3-R2 maps direct high-confidence correspondences:
- face
- mouth
- left/right eye white
- left/right iris
- left/right brow
- front/back hair
- topwear → cloth
- headwear/eyewear/earwear/tail/wings/objects → accessory

Unknown tags remain unknown and are surfaced by P3-R1 as `semantic-unsupported`.

P3-R2 does not synthesize `body`, side hair, or landmarks from weak heuristics. That is P3-R3/P3-R5 work.

## Image codec

`PillowImageCodec` is the production codec and is imported lazily. The core service and CI remain zero-dependency.

A dependency-free PNG encoder is included only for sending the RGBA source image to the See-through subprocess.

## Phase-2 bridge

`to_rig_compiler_inputs()` is the only P3→P2 data conversion:
- layer records → `SemanticLayer`
- normalized bbox → `NormalizedRect`
- A8 → `AlphaMask`
- RGBA → `RgbaImage`
- normalized landmarks → `Landmark`
- `sourceRevision` preserved

`decompose_and_compile()` and `decode_decompose_and_compile()` compose this bridge with the existing P2 `compile_avatar()` release gate.

## Determinism

Determinism is required for:
- command construction
- model tag interpretation
- depth-to-z ordering with tag tie-break
- source canvas transform
- bridge construction

Real diffusion inference can still be hardware-sensitive; the adapter always supplies a fixed seed and records backend revision in the P3 source revision.
