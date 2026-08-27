# Phase 3 R6 Status — Quality Scoring

Status: **IMPLEMENTED / DRAFT PR**

## Delivered

- `CharacterQualityReportV1`
- `QualityDecision`: `pass`, `retry`, `manual_review`, `block`
- six deterministic weighted quality dimensions
- stable quality findings and machine-readable actions
- direct consumption of P3 findings and P2 `CompileQaReportV1`
- automatic retry/manual-review/block classification
- export gate separated from preview artifact availability
- Bridge integration through `SingleImageCompileResultV1.quality`
- `quality_scoring_enabled=False` debug opt-out
- JSON Schema: `spec/character-quality-report.schema.json`

## Default weights

```text
semantic     25
completion   20
landmark     20
consistency  10
synthetic    10
compiler     15
```

## Default thresholds

```text
PASS          >= 85, no retry/manual action
MANUAL_REVIEW >= 70 when no retry action
RETRY         < 70 or automatic retry action
BLOCK         any P3 error or P2 QA not ready
```

## Artifact behavior

`RETRY` and `MANUAL_REVIEW` keep a successful `.a2d` artifact for preview. `ready_for_export` is true only for `PASS`.

## Validation target

P3-R6 adds 15 Decomposer tests. Expected full Decomposer suite after this change: **82 tests**.

The suite covers:

- clean PASS
- missing/low-confidence completion → RETRY
- pair inconsistency → MANUAL_REVIEW
- synthetic provenance → MANUAL_REVIEW
- low landmark confidence → provider retry
- low but ready P2 score → compiler review
- P2 hard failure → BLOCK
- P3 hard failure → BLOCK
- missing compiler integration → BLOCK
- completed body proxy penalty reduction
- deterministic report serialization
- invalid weight config
- Bridge quality generation while keeping preview `.a2d`
- Bridge quality-scoring opt-out

## Remaining Phase 3

```text
P3-R1 Decomposer Contract       ✅
P3-R2 Production Adapter        ✅
P3-R3 Semantic Refinement       ✅
P3-R4 Occlusion Completion      ✅
P3-R5 Landmark Fusion           ✅
P3-R6 Quality Scoring           ✅ implementation
P3-R7 Real Single-image E2E     NEXT
```

## P3-R7 gate

P3-R7 must validate this scoring contract on real GPU inference and real character images. Thresholds should not be called production-final until the corpus produces stable false-pass / false-retry rates.
