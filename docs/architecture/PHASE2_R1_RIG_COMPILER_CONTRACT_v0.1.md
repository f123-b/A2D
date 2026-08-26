# Phase 2 R1 — Rig Compiler Contract v0.1

Status: **FROZEN FOR IMPLEMENTATION**

## Boundary

Input is a renderer-independent normalized semantic layer package. Output of R1 is a deterministic `RigPlanV1`; later R2/R3 stages materialize mesh/buffers and final Avatar IR.

```text
Decomposer / PSD importer
        ↓
NormalizedLayerPackage v1
        ↓
Rig Compiler
        ↓
RigPlanV1
        ↓
Mesh / Deformer / Physics compiler
        ↓
R8B-equivalent Avatar IR
```

## Coordinate contract

- all layer bounding boxes use normalized canvas coordinates `[0,1]`
- all landmarks use normalized canvas coordinates `[0,1]`
- compiler input is resolution-independent after normalization
- image/mask URIs reference assets owned by the input package

## Canonical semantic vocabulary

Core:
- body
- cloth
- face
- brow_l / brow_r
- eye_white_l / eye_white_r
- iris_l / iris_r
- mouth
- hair_front
- hair_side_l / hair_side_r
- hair_back
- accessory

R1 requires body, face, both eye whites, both irises and mouth. Brows/hair are optional but produce explicit QA warnings when absent.

## Deterministic output

For identical normalized input, `compile_rig_plan()` must produce identical:
- canonical part IDs
- parent hierarchy
- draw order
- parameter list
- physics rule IDs
- expression rule IDs
- QA ordering

No random sampling is permitted in R1.

## R8B target

The plan exposes the complete Phase-1 standard parameter set plus:
- ParamHairFrontX
- ParamHairSideLX
- ParamHairSideRX
- ParamHairBackX

Canonical expressions:
- happy
- surprised
- angry

Hair semantic layers generate deterministic spring-chain rules.

## QA policy

Compiler must reject:
- duplicate layer IDs
- duplicate canonical semantic slots
- invalid normalized bounding boxes
- missing parent layer references
- self-parenting
- missing required standard semantics

Compiler must report, not silently discard:
- missing optional brow/hair semantics
- low-confidence semantic layers

## Next milestone: P2-R2

Implement normalized landmarks + adaptive mesh generation:
- contour extraction
- feature-point preservation
- adaptive sampling
- triangulation
- mesh quality checks
- deterministic binary geometry output
