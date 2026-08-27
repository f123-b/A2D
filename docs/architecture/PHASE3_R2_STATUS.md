# Phase 3 R2 Status

Status: implementation ready for stacked PR validation.

## Implemented

- `SeeThroughProcessBackend`
- official `inference/scripts/inference_psd.py` process invocation
- explicit seed, checkpoints, resolutions, steps, timeout and offload flags
- dependency-free RGBA8 PNG writer for subprocess input
- lazy `PillowImageCodec` for production PNG/JPG and layer raster IO
- direct `optimized/info.json + part PNG` parser
- center-square padding removal and source-pixel remap
- depth-median → deterministic back-to-front z-order
- See-through V3 tag mapping for direct A2D semantics
- semantic parent hints for iris/eye/brow/mouth/hair
- structured process/output errors
- P3 normalized result → P2 compiler input bridge
- encoded-image → decompose → normalize → `compile_avatar()` orchestration

## Tests added

P3-R2 adds 12 tests:
- 7 production adapter tests
- 5 P3→P2 bridge tests

Together with P3-R1 this yields 29 decomposer tests.

## Deliberate non-goals

- no PyTorch/CUDA/model weights in A2D CI
- no PSD parsing
- no fake body synthesis from topwear
- no fake landmark estimation
- no side-hair invention
- no claim of real GPU See-through inference in GitHub Actions

## External runtime

A production machine prepares the upstream See-through repository/environment separately. A2D points `SeeThroughConfig.repo_root` at that pinned checkout.

## Next

P3-R3 Semantic Refinement:
- required-semantic completion
- body proxy/matte synthesis
- side-hair inference
- eye/brow pairing repair
- conflict resolution and confidence propagation
