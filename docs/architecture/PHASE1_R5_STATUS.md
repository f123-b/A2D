# Phase 1 — R5 Status

Status: **PASS / PHYSICS v1 FROZEN**

## Implemented

### Fixed-step scheduler
- default 120 Hz
- frame-dt clamp
- max substep cap
- spiral-of-death protection

### Spring-chain solver
- typed-array node state
- Verlet-style prediction
- four distance-constraint iterations
- root inertial drive
- gravity
- damping
- stiffness
- finite-number protection
- maximum-displacement protection
- automatic reset on invalid state

### Avatar IR
Physics is now serialized in `.a2d`:
- node count
- segment length
- root
- gravity
- damping
- stiffness
- input parameter bindings
- output parameter bindings
- max displacement

Loader validates:
- duplicate physics IDs
- node count
- stiffness/damping range
- input/output parameter references
- output min/max

### Runtime integration

```text
Tracking / UI
     |
ParameterCore
     |
FixedStepPhysics @120Hz
     |
Physics output parameters
     |
dirty ParameterState
     |
GPU Morph / Deformer
```

The browser demo now uses the real R4 GPU deformation renderer plus R5 physics.

## Golden validation

Input:
- `ParamAngleX = 0` before 0.5 s
- `ParamAngleX = 20` after 0.5 s
- 2 second simulation

Render rates:
- 30 FPS
- 60 FPS
- 120 FPS

Result:
- final `ParamHairX`: `-0.15805485844612122`
- maximum final cross-rate delta: `0`
- acceptance tolerance: `1e-3`

Long-run:
- 60 seconds
- changing sinusoidal head input
- all state finite
- max absolute `ParamHairX`: `0.6569243669509888`

## Strict TypeScript validation

Passed for:
- Avatar IR schema types
- package loader
- ParameterCore
- deformation reference
- deformation buffers
- WebGL2 reference renderer
- WebGL2 GPU deformation renderer
- physics
- physics factory

Actual compiled TypeScript solver was executed under Node.js v22.16.0 and matched the canonical physics golden data with zero error.

## JSON Schema validation

`r5-golden.a2d/model.json`:
- Draft 2020-12 errors: `0`

## Physics microbenchmark

Node.js v22.16.0, 5 nodes/chain, 4 constraint iterations:

| Chains | Physics frame |
|---:|---:|
| 1 | ~2.54 us |
| 10 | ~9.47 us |
| 100 | ~87.14 us |

This is a CPU microbenchmark, not a browser/GPU performance guarantee.

The current result is comfortably below the Phase-0 `<1 ms physics` target for 100 short chains in this environment.

## Deliberately not included in Physics v1
- collision
- self-collision
- cloth surface constraints
- XPBD
- wind fields
- GPU physics

Those remain later-stage features.

## Next gate

**R6 — WebGPU backend**

Requirements:
1. consume the same Avatar IR
2. consume the same parameter normalization
3. consume the same morph influence records
4. consume the same pseudo3d equations
5. keep static model data GPU-resident
6. use storage/uniform buffers instead of WebGL2 texture emulation
7. match CPU golden deformation vectors within `1e-4`
8. benchmark against WebGL2 at 10k / 25k / 50k vertices
