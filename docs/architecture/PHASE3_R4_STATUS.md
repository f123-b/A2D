# Phase 3 R4 Status

Status: implementation ready for stacked PR validation.

## Implemented

- `CompletionProvider` protocol
- `CompletionRequestV1` / `CompletionResponseV1`
- `OcclusionCompletionConfig`
- deterministic semantic occluder projection
- face-hole detection under front/side hair
- body-hole detection under cloth
- full completion request for P3-R3 body proxy
- strict visible-pixel byte preservation gate
- provider identity/revision validation
- provider output size/confidence validation
- structured provider failure findings
- completion confidence warnings
- deterministic source revision update
- `DeterministicReferenceCompletionProvider`
- one-click bridge ordering: normalize → refine → complete → P2
- independent `complete_hidden=False` debug switch

## Validation target

P3-R4 adds 12 decomposer tests, raising the expected Decomposer suite from 41 to 53 tests.

The new suite covers:
- reference fill behavior
- visible-pixel preservation
- face hole completion under hair
- missing-provider warning path
- provider mutation rejection
- invalid provider output rejection
- body proxy completion
- low-confidence propagation
- no-op provider behavior when no occlusion exists
- deterministic output/revision
- invalid config rejection
- P3-R4 → P2 → `.a2d` end-to-end integration

## Deliberate limitations

- reference completion is not production visual inpainting
- no claim of GPU inpainting/model quality in GitHub Actions
- no bbox expansion for hidden anatomy in v0.1
- no landmark inference in this stage
- no visible-pixel rewriting by any provider

## Next

P3-R5 Landmark Fusion:
- provider ABI for face/anime landmarks
- canonical landmark normalization
- multi-provider confidence fusion
- geometry fallbacks
- hair-root estimation
- pair consistency and QA
