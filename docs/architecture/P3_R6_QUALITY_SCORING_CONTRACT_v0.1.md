# P3-R6 Quality Scoring Contract v0.1

## Goal

Convert all Phase-3 evidence plus the Phase-2 compile QA result into one deterministic release decision that Studio can execute without reinterpreting raw warnings.

```text
DecomposerResultV1
        +
OneClickCompileResultV1.qa
        ↓
score_character_quality()
        ↓
CharacterQualityReportV1
        ↓
PASS / RETRY / MANUAL_REVIEW / BLOCK
```

## Report contract

`CharacterQualityReportV1` contains:

- `decision`
- `score` in `0..100`
- `ready_for_export`
- error/warning/info counts
- six dimension scores
- normalized quality findings
- machine-readable recommended actions

The serialized contract is `spec/character-quality-report.schema.json`.

## Dimensions

Default weights are frozen at v0.1:

| Dimension | Weight | Evidence |
| --- | ---: | --- |
| semantic | 25 | required layer presence and confidence |
| completion | 20 | required/completed/missing/low-confidence hidden-pixel completion |
| landmark | 20 | expected landmark coverage/confidence and disagreement |
| consistency | 10 | pair geometry/confidence and repaired draw order |
| synthetic | 10 | body proxy, mirrored pair and side-hair provenance |
| compiler | 15 | Phase-2 `CompileQaReportV1.score` and `ready` |

Weights must be non-negative integers and sum to exactly 100.

## Semantic score

The required semantic set remains:

```text
body
face
eye_white_l
eye_white_r
iris_l
iris_r
mouth
```

The dimension score is the average required-layer confidence. Missing required semantics produce quality errors and an automatic `rerun_decomposition` action.

Required layer confidence below `0.65` requests a decomposition retry.

## Completion score

Completion is evaluated per target only when P3-R4 emitted `occlusion-completion-required`.

```text
completed, normal confidence  = 100
completed, low confidence     = 55
provider missing              = 35
required but unresolved       = 20
```

Missing/weak completion produces `run_completion` actions.

No completion requirement means the dimension score is 100.

## Landmark score

The base expected set is:

```text
head_center
nose
neck
eye_l_center
eye_r_center
iris_l_center
iris_r_center
mouth_center
```

Brow centers and hair roots become expected when the corresponding semantic layers exist.

The base landmark score is average expected-landmark confidence. Missing or `<0.65` landmarks request `run_landmark_provider`.

`landmark-disagreement` applies an additional bounded penalty and adds manual `review_landmarks`.

## Consistency score

Deterministic penalties:

```text
semantic-pair-geometry-mismatch    -20
semantic-pair-confidence-mismatch  -10
semantic-z-order-corrected          -5
```

Pair mismatches request manual semantic review. A corrected z-order is recorded but does not by itself force manual review.

## Synthetic score

Provenance remains explicit:

```text
body-proxy-synthesized        -35
body proxy after completion   -15
semantic-pair-mirrored        -12 each
side-hair-synthesized          -8 each
```

Synthetic content is not a compiler error. It requests manual review while preserving the preview artifact.

## Compiler score

The compiler dimension directly consumes `CompileQaReportV1.score`.

- `qa.ready == false` is a hard `BLOCK`;
- missing compiler/QA for otherwise-ready P3 is a hard integration error;
- ready compiler score below 85 requests `review_compiler`.

If P3 is already blocked, P2 is marked as skipped rather than producing a second false compiler error.

## Decision policy

Hard blockers always win:

```text
P3 error
or P2 qa.ready == false
        ↓
BLOCK
```

Then actionability wins over the aggregate score:

```text
automatic retry action present  → RETRY
manual review action present     → MANUAL_REVIEW
```

Otherwise:

```text
score >= 85        → PASS
70 <= score < 85   → MANUAL_REVIEW
score < 70         → RETRY
```

Only `PASS` sets `ready_for_export=true`.

## Artifact policy

Quality scoring is an export/publish gate, not a destructive compiler gate.

A P2 artifact that compiled successfully remains available when the quality decision is `RETRY` or `MANUAL_REVIEW`. Studio can preview the avatar, show actions, let the user repair it, and re-score.

`BLOCK` means the upstream or compiler contract itself is invalid and automatic export is prohibited.

## Determinism

For identical Decomposer results, P2 QA and configuration:

- dimension ordering is stable;
- finding ordering is stable;
- action ordering is stable;
- score/decision are stable;
- `to_dict()` is byte-order-independent canonical data for JSON serialization.

## Non-goals

P3-R6 does not:

- judge subjective illustration aesthetics;
- run a learned perceptual model;
- validate real GPU rendering;
- delete preview artifacts for non-PASS decisions;
- replace P2 structural QA.

These production gates are part of P3-R7 / later release validation.
