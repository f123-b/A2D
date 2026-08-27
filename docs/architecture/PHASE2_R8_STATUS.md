# Phase 2 R8 Status

Status: implementation ready for stacked PR validation on `feat/one-click-compiler`.

## Implemented

- public `compile_avatar()` Phase-2 orchestration API
- structured failure conversion for contract / mesh / rig / proxy-Z / morph / physics / package failures
- hard `QA.ready` packaging gate
- deterministic single RGBA8 atlas
- replicated atlas gutters and texel-center UV remap
- multiple accessory preservation by source layer ID
- little-endian 4-byte-aligned geometry builder
- per-part positions / UVs / indices / Proxy-Z / influence ranges
- global P2-R5 morph influence table with range rebasing
- whole-head Proxy-Z materialization using P2-R4 profile + semantic biases
- Runtime-compatible P2-R6 physics serialization
- expression serialization
- semantic deformer serialization, including translation→warp Avatar IR v1 compatibility mapping
- iris clipping relationships
- canonical JSON
- deterministic ZIP member order / timestamp / mode / STORE compression
- `qa/report.json`
- package SHA-256

## Artifact policy

```text
QA.ready == false → artifact is None
QA.ready == true  → model + buffers + atlas + qa/report + .a2d
```

A packaging failure after a successful P2-R7 report adds a `cross_stage / compile-package-failed` blocker and suppresses the artifact.

## Tests added

P2-R8 adds 10 end-to-end repository tests covering:
- ready package and required members
- single atlas/material references
- buffer alignment and global morph range bounds
- iris clipping + head pseudo3D materialization
- byte-level determinism and SHA-256
- missing mask structured blocker
- image/mask dimension structured blocker
- atlas capacity packaging blocker
- accessory preservation
- Runtime physics/expression payloads

Expected Rig Compiler suite after integration: 74 tests.

## Phase 2 exit condition

P2-R8 closes the Auto Rig Compiler implementation path. The remaining release work is integration validation against the Phase-1 package loader/renderer and representative decomposer outputs; algorithm stages P2-R1..R8 are now connected through one publish gate.

## Next

Phase 3 — Automatic Decomposition:

```text
single character image
      ↓
semantic layer decomposition
      ↓
normalized layers + RGBA + masks + landmarks
      ↓
P2 compile_avatar()
      ↓
.a2d
```
