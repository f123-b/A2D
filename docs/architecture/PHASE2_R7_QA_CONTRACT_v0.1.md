# Phase 2 R7 — Cross-stage QA Contract v0.1

## Purpose

P2-R7 is the single deterministic release gate between compiler stages P2-R1..R6 and the P2-R8 `.a2d` packager.

It does not repair geometry or silently clamp bad data. It aggregates warnings and rejects ABI/structural violations before packaging.

## Inputs

- `NormalizedRigInput`
- `RigPlanV1`
- semantic `AdaptiveMesh` outputs
- `SemanticRigPlanV1`
- `ProxyZHeadPlanV1`
- semantic `CompiledMorphPlanV1` outputs
- `AutoPhysicsPlanV1`

## Output

`CompileQaReportV1`:

```text
version
characterId
ready
score
errors
warnings
infos
findings[]
stages[]
```

The JSON representation is frozen by `spec/compile-qa-report.schema.json`.

## Severity policy

### error

Blocks packaging:

```text
ready = false
```

Examples:
- missing required mesh/stage output
- vertex/UV count mismatch
- out-of-range triangle index
- Proxy-Z count mismatch
- invalid Proxy-Z Runtime range
- non-contiguous or out-of-range morph ranges
- >8 morph influences per vertex
- morph parameter index outside parameter table
- missing/unplanned physics chain
- physics binding referencing an unknown parameter
- cross-stage character ID mismatch

### warning

Does not block packaging, but reduces score.

Examples:
- P2-R1 low semantic confidence
- P2-R2 mesh quality guidance
- P2-R3 bbox pivot fallback
- P2-R4 missing nose fallback
- P2-R6 non-vertical hair geometry

### info

No score penalty. Used for intentionally unassessed/non-blocking conditions.

## Ready policy

`ready` is independent of score:

```text
ready = errors == 0
```

Warnings never silently become blockers because of an arbitrary score threshold.

The quality score is diagnostic:

```text
score = clamp(100 - 25*errors - 4*warnings, 0, 100)
```

Default penalties are configurable for UI/reporting, but the strict `ready` gate remains error-driven.

## Mesh checks

For every canonical non-accessory planned part:
- compiled mesh must exist
- at least 3 vertices
- UV count equals vertex count
- `MeshQuality.vertex_count` matches actual positions
- coverage >= 0.45 hard minimum
- retained triangle minimum angle >= 1.99° hard minimum
- all positions finite
- triangle indices in range
- stage-local mesh findings are preserved

Multiple accessories are not yet representable by the current semantic-keyed mesh map. Their QA emits an `info` record rather than pretending to have verified them.

## Proxy-Z checks

- P2-R4 output required
- character ID parity
- `proxy_z` count equals face vertex count
- non-empty
- finite and inside compiler Runtime range `[-0.25, 1.25]`
- finite pivot/radius/depth/perspective/gains
- positive radius and depth scale
- P2-R4 findings preserved

Negative Proxy-Z down to `-0.25` is legal: semantic ear/back-face depth may sit behind the neutral face plane.

## Morph checks

P2-R7 derives required morph semantics from `SemanticRigPlanV1.morph_intents`.

For each required semantic:
- plan exists
- semantic matches
- one vertex range per mesh vertex
- ranges are contiguous
- ranges stay inside record buffer
- `count <= 8` Runtime v1 gate
- records in each range reference that vertex
- ranges cover every record exactly
- `parameterIndex < len(RigPlanV1.parameter_ids)`
- finite deltas/weights
- weights in `[0,1]`

## Physics checks

- P2-R6 required when RigPlan has physics rules
- character ID parity
- planned and compiled chain ID sets match exactly
- nodeCount >= 2
- finite positive segmentLength
- damping/stiffness in `[0,1]`
- every input/output parameter exists in the RigPlan parameter table
- P2-R6 findings preserved

## Determinism

Finding order is frozen by:
1. severity (`error`, `warning`, `info`)
2. stage order
3. code
4. subject ID
5. message

Duplicate identical findings are collapsed.

Stage summaries always use this order:
1. contract
2. mesh
3. semantic_rig
4. proxy_z
5. morph
6. physics
7. cross_stage

Equivalent compiler outputs must therefore serialize to the same QA JSON independent of input mapping insertion order.
