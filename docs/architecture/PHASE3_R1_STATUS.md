# Phase 3 R1 Status

Status: implementation ready for stacked PR validation on `feat/decomposer-contract`.

## Implemented

- model-independent `DecompositionBackend` protocol
- strict RGBA source image contract
- strict backend layer/landmark observation contract
- semantic alias normalization into P2 vocabulary
- landmark alias normalization into P2 pivot vocabulary
- deterministic canonical IDs
- multi-accessory support
- tight alpha-mask crop
- RGBA alpha × segmentation-mask materialization
- normalized `[0,1]` bbox/landmark coordinates
- deterministic package-relative RGBA/A8 asset paths
- parent resolution and cycle rejection
- explicit unsupported-label findings
- low-confidence warnings
- deterministic `sourceRevision`
- JSON-ready normalized layer package output
- zero-dependency scripted reference backend

## Validation

17 P3-R1 unit tests cover source validation, aliases, crop math, alpha composition, duplicate semantics, multi-accessory determinism, unsupported labels, empty masks, parent resolution/cycles, landmark normalization, confidence findings, package shape, source revision and backend protocol invocation.

## CI

A dedicated Decomposer job runs Python 3.11 `compileall`, all decomposer unit tests, and parses the shared normalized-layer JSON Schema.

## Not claimed in R1

P3-R1 does not claim real AI decomposition quality. No segmentation or landmark ML model is embedded yet.

## Next — P3-R2

Implement the first production adapter and orchestration path:

```text
flat PNG/JPG
  ↓
decode RGBA
  ↓
segmentation + landmarks backend
  ↓
P3-R1 normalization
  ↓
bridge assets to P2 RgbaImage/AlphaMask
  ↓
compile_avatar()
  ↓
.a2d
```
