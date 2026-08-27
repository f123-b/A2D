# Phase 3 R3 Status

Status: implementation complete; pending stacked PR CI validation.

## Implemented

- `SemanticRefinementConfig`
- `refine_decomposer_result()`
- conservative body proxy from cloth matte
- one-sided eye/iris/brow mirror repair
- side-hair extraction from real hair pixels
- pair geometry/confidence consistency warnings
- deterministic core z-order repair
- canonical parent graph hints
- confidence penalties for every synthesized semantic
- blocking required-semantic completion gate
- refined source revision
- P3→P2 bridge refinement enabled by default
- debug opt-out via `refine_semantics=False`

## Tests added

12 P3-R3 tests cover:
- body proxy synthesis
- existing body preservation
- eye/iris mirror repair
- required pair failure
- side-hair extraction
- pair mismatch warning
- z-order conflict repair
- canonical parent graph
- deterministic output/revision
- refined one-click P3→P2 `.a2d`
- debug opt-out
- config validation

Expected Decomposer suite after P3-R3: 41 tests.

## Deliberate non-goals

- no generative/inpainting completion
- no landmark inference
- no real See-through GPU execution in CI
- no synthetic pair when both sides are missing
- no side hair without real hair pixels

## Next

P3-R4 Occlusion Completion.
