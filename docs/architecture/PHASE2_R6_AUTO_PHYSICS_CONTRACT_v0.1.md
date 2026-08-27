# Phase 2 R6 — Auto Physics Compiler Contract v0.1

## Purpose

P2-R6 converts optional semantic hair layers into deterministic `spring_chain` Runtime configurations without changing the Phase-1 physics schema.

Inputs:
- `NormalizedRigInput`
- P2-R1 `RigPlanV1`
- P2-R2 `AdaptiveMesh` per present hair semantic
- P2-R3 `SemanticRigPlanV1` root pivots

Output:
- `AutoPhysicsPlanV1`
- one `RuntimeSpringChainV1` per present hair semantic
- explicit QA findings

## Supported semantics

Canonical order:
1. `hair_front`
2. `hair_side_l`
3. `hair_side_r`
4. `hair_back`

Outputs:
- `ParamHairFrontX`
- `ParamHairSideLX`
- `ParamHairSideRX`
- `ParamHairBackX`

A present hair layer without a mesh is a compiler error. Missing optional hair layers simply produce no chain.

## Geometry contract

All mesh positions and roots are normalized to `[0,1]`.

The effective chain length is:

```text
max(mesh.y) - root.y
```

`nodeCount` is derived from effective geometry length and a semantic target segment length, then clamped to semantic bounds.

Standard R8B-like geometry resolves to:
- front: 6 nodes
- left side: 7 nodes
- right side: 7 nodes
- back: 8 nodes

The final segment length is exact:

```text
segmentLength = effectiveLength / (nodeCount - 1)
```

so the neutral chain spans the measured root-to-tip vertical extent.

## Root contract

Root pivots come from P2-R3.

Root-source metadata is:
- `landmark` when a matching `hair_*_root` landmark with confidence >= 0.5 exists
- `bbox` otherwise

P2-R6 does not independently guess a second root.

## Dynamic presets

Semantic presets define reference behavior, then geometry length applies bounded modulation.

| semantic | target segment | damping | stiffness | gravity Y | output gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| front | 0.052 | 0.10 | 0.92 | 0.58 | 2.0 |
| side | 0.075 | 0.12 | 0.90 | 0.62 | 1.8 |
| back | 0.068 | 0.14 | 0.88 | 0.68 | 1.3 |

Longer hair receives slightly more damping/gravity and slightly less stiffness. Output gain is normalized against semantic reference length.

All chains keep the existing R8B inertial root drives:
- `ParamAngleX`, x, gain `0.0025`
- `ParamBodyAngleX`, x, gain `0.0012`

Output is `tip.x`, clamped to `[-1,1]`.

## Runtime ABI

`RuntimeSpringChainV1.to_avatar_ir()` emits the existing Phase-1 shape:

```text
id
type = spring_chain
nodeCount
segmentLength
root [x,y]
gravity [x,y]
damping
stiffness
inputBindings
outputBindings
maxDisplacement
```

No new avatar-schema field is introduced.

## Runtime v1 direction limitation

The Phase-1 solver initializes every chain in `+Y`. It has no chain-orientation field.

P2-R6 estimates the root-to-tip direction only for QA. If verticality is below `0.55`, it emits:

```text
physics-nonvertical-geometry
```

It does not silently rotate geometry or create a renderer-only extension.

## Failure policy

Reject:
- unsupported physics semantic
- wrong output parameter
- missing mesh for a present hair layer
- non-finite/out-of-range mesh coordinates
- non-finite/out-of-range root
- fewer than two vertices
- zero root-to-tip extent
- hair that does not extend below its root
- invalid compiler thresholds

Warn:
- non-vertical root-to-tip geometry
- very short generated segments

## Determinism

Equivalent inputs must produce the same Runtime spring-chain fields independent of mesh vertex ordering.
