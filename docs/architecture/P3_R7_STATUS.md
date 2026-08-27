# P3-R7 Status

Status: **implementation complete / production GPU validation pending external execution**.

## Implemented

- `a2d_decomposer.e2e`
  - `E2EMode`
  - `E2EGate`
  - `RuntimeSmokeV1`
  - `SingleImageE2EPreflightV1`
  - `SingleImageE2EReportV1`
  - artifact/source SHA verification
  - deterministic bundle writer
  - final gate evaluation
- production CLI `a2d-single-image-e2e`
- provider factory loading via `module:attribute`
- deterministic reference single-image generator
- TypeScript Runtime package smoke using `loadA2DFromZip()`
- `single-image-e2e-report.schema.json`
- CI cross-language reference E2E job
- unit tests for PASS / FAIL / NOT_RUN and production backend enforcement

## Acceptance split

### CI reference acceptance

Must pass automatically on GitHub Actions:

```text
Python P3/P2 pipeline
→ character.a2d
→ TypeScript Runtime Loader
→ finalized e2e-report.json gate=pass
```

### Production acceptance

Requires a machine with the pinned See-through repository/weights and a real character image. The final production report must show:

```text
mode = production
backend.name = see-through
qualityDecision = pass
readyForExport = true
runtime.passed = true
gate = pass
```

The current repository/CI environment has no production CUDA model execution evidence, so that external acceptance remains intentionally unclaimed.

## Phase 3 status

```text
P3-R1 Decomposer Contract       ✅
P3-R2 Production Adapter        ✅
P3-R3 Semantic Refinement       ✅
P3-R4 Occlusion Completion      ✅
P3-R5 Landmark Fusion           ✅
P3-R6 Quality Scoring           ✅
P3-R7 E2E Harness/Runtime Gate  ✅
P3-R7 Real GPU evidence         ⏳ external production run
```
