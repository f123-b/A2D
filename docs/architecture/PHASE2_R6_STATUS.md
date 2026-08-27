# Phase 2 R6 Status

Status: implementation complete on `feat/auto-physics`; hardware-independent CI validation required before the PR is considered complete.

## Implemented

- deterministic `AutoPhysicsPlanV1`
- front / side-L / side-R / back hair chains
- P2-R3 semantic root reuse
- explicit landmark-vs-bbox root provenance
- geometry-derived node count
- exact root-to-tip segment length
- semantic spring presets
- bounded length-based damping / stiffness / gravity adjustment
- normalized output gain
- existing R8B head/body inertial inputs
- existing Phase-1 Runtime IR serialization
- non-vertical geometry QA warning
- short-segment QA warning
- strict invalid geometry / missing mesh rejection

## Runtime compatibility

No `AvatarModelV1` schema change.

Generated chains map directly to the existing `SpringChainPhysics` fields and current 120 Hz fixed-step solver.

## Standard target

R8B-like hair geometry should resolve to:

```text
hair_front   6 nodes
hair_side_l  7 nodes
hair_side_r  7 nodes
hair_back    8 nodes
```

## Next

P2-R7 QA:
- cross-stage structural validation
- mesh / proxy-Z / morph / physics quality aggregation
- error/warning severity policy
- compile readiness score
- deterministic QA report
