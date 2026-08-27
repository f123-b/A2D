# Phase 3 R5 Status

Status: implementation ready for stacked PR validation.

## Implemented

- `LandmarkProvider` protocol
- `LandmarkCandidateV1`
- `LandmarkFusionConfig`
- `ScriptedReferenceLandmarkProvider`
- canonical provider alias normalization
- provider identity/revision validation
- alpha-weighted semantic centroids
- top-band hair root extraction
- conservative nose and neck geometry fallback
- exact preservation of high-confidence existing landmarks
- weighted fusion for agreeing candidates
- strongest-source selection for disagreements
- confidence penalty + `landmark-disagreement`
- stale low-confidence finding replacement
- deterministic revision and output ordering
- default bridge order:
  `normalize → refine → complete → fuse landmarks → P2`
- debug opt-out through `fuse_landmarks_enabled=False`

## Validation target

P3-R5 adds 14 tests.

Together with P3-R1 through P3-R4, the expected Decomposer suite is:

```text
67 tests
67 PASS
```

Coverage includes:

- standard P2 landmark completion from geometry
- conservative nose confidence
- exact high-confidence landmark preservation
- provider alias fusion
- large provider/geometry disagreement
- duplicate provider landmark rejection
- provider exception rejection
- unsupported provider landmark handling
- top-band hair roots
- neck geometry
- determinism/revision
- P3-R5 → P2 → real `.a2d`
- bridge debug opt-out
- config validation

## Deliberate non-goals

- no claim that bbox/alpha geometry equals a trained landmark detector
- no MediaPipe-specific types in core
- no hard dependency on a landmark model/runtime
- no ear/cheek landmark synthesis
- no quality release score yet

## Next

P3-R6 Quality Scoring:
- aggregate findings and provenance across P3 stages
- semantic/completion/landmark sub-scores
- release/retry/manual-review decisions
- Studio-facing quality report
