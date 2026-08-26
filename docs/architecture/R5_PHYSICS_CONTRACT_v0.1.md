# R5 Physics Contract v0.1

Status: **FROZEN FOR IMPLEMENTATION**

## Goals

- Physics behavior must not depend directly on render FPS.
- Runtime behavior must remain deterministic for the same fixed-step input sequence.
- Physics outputs are compact parameter values, never full deformed vertex arrays.
- Physics state must be stored in typed arrays / SoA-friendly structures.
- No NaN/Inf propagation into the renderer.
- The TypeScript reference implementation is the correctness oracle for the later Rust/WASM implementation.

## Fixed timestep

Default:

```text
physicsHz = 120 Hz
fixedDt   = 1 / 120 s
maxFrameDt = 0.1 s
maxSubSteps = 12
```

Render frame:

```text
render dt
   ↓ clamp
accumulator += dt
   ↓
while accumulator >= fixedDt
   physics.step(fixedDt)
   accumulator -= fixedDt
```

Excess accumulated time beyond the configured substep cap is dropped intentionally.
This prevents the "spiral of death".

## Spring-chain v1 model

A chain consists of:

```text
root ─ p1 ─ p2 ─ ... ─ pn
```

The root is kinematic.

Each dynamic node stores:

```text
position
previousPosition
restLength
inverseMass
```

The solver uses Verlet-style prediction plus distance constraints and damping.

### External drive

A chain can be driven by normalized avatar parameters such as:

```text
ParamAngleX
ParamAngleY
ParamBodyAngleX
```

Drive is converted into root acceleration / inertial displacement.

### Forces

v1 supports:
- gravity
- inertial drive
- damping
- distance constraint stiffness

No collision or self-collision in v1.

## Stability

Required guards:
- clamp frame dt
- finite-number checks
- bounded parameter outputs
- minimum segment length epsilon
- configurable max displacement
- reset chain if state becomes invalid

## Physics output

A chain writes one or more scalar outputs.

Typical hair chain:

```text
tip displacement X -> ParamHairFrontX
tip displacement Y -> ParamHairFrontY
```

Output pipeline:

```text
chain state
  ↓
measure
  ↓
gain
  ↓
clamp
  ↓
smoothing optional
  ↓
ParameterCore.set(...)
```

The renderer only observes ParameterCore.

## Determinism contract

Given:
- same initial state
- same fixed dt
- same input parameter sequence

the reference implementation must produce the same output within floating-point tolerance.

Cross-render-rate acceptance:
- simulate identical wall-clock duration at 30, 60 and 120 render FPS
- final scalar physics outputs differ by <= 1e-3

## R5 exit criteria

- fixed-step scheduler implemented
- spring-chain solver implemented
- typed state storage
- physics-to-parameter output bindings
- finite/reset protection
- 30/60/120 FPS golden validation
- long-run stability test
