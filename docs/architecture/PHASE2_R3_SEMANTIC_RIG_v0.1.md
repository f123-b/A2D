# Phase 2 R3 — Semantic Rig Contract v0.1

Status: **FROZEN FOR REFERENCE IMPLEMENTATION**

## Purpose

P2-R3 converts the structural `RigPlanV1` from P2-R1 into a deterministic semantic motion plan.
It does **not** generate final vertex deltas and it does **not** generate proxy-Z depth.

```text
NormalizedLayerPackage
        ↓
RigPlanV1
        ↓
SemanticRigPlanV1
        ├─ pivots
        ├─ deformer tree
        ├─ parameter bindings
        └─ morph intents
        ↓
P2-R4 Proxy-Z Head
P2-R5 Facial Morph Compiler
```

The semantic rig layer must remain independent of renderer APIs and mesh topology.

## Deformer tree

Canonical standard-avatar order:

```text
body-motion
└─ head-pseudo3d
   ├─ eye-l-blink
   │  └─ iris-l-gaze
   ├─ eye-r-blink
   │  └─ iris-r-gaze
   ├─ mouth-morph
   ├─ brow-l-motion
   ├─ brow-r-motion
   ├─ hair-side-l-physics
   ├─ hair-side-r-physics
   └─ hair-front-physics

body-motion
└─ hair-back-physics
```

Optional semantic layers prune their corresponding deformer nodes.

## Pivot policy

A semantic pivot is resolved from normalized landmarks first. Aliases are deterministic and never depend on input order.

Critical preferred landmarks:
- body: `neck`, `neck_center`
- face: `head_center`, `face_center`, `nose`
- left/right eye: `eye_l_center`, `eye_r_center`
- mouth: `mouth_center`

If a critical pivot has no landmark with confidence >= 0.5, the compiler falls back to the layer bbox and emits `warning / pivot-bbox-fallback`.

Fallback formulas:
- body: `(bbox center X, bbox top + 15% height)`
- hair: `(bbox center X, bbox top + 8% height)`
- other layers: bbox center

## Parameter binding rules

### Head
- `ParamAngleX` -> yaw, -30..30 degrees
- `ParamAngleY` -> pitch, -30..30 degrees
- `ParamAngleZ` -> roll, -30..30 degrees

### Body
- `ParamBodyAngleX` -> horizontal body motion
- `ParamBodyAngleY` -> vertical body motion
- `ParamBodyAngleZ` -> body roll
- `ParamBreath` -> body breath morph intent

### Eyes
- `ParamEyeLOpen` / `ParamEyeROpen` -> independent blink morph
- `ParamEyeBallX` / `ParamEyeBallY` -> iris translation

### Mouth
- `ParamMouthOpenY` -> mouth open morph
- `ParamMouthForm` -> mouth form morph

### Brows
- `ParamBrowLY` / `ParamBrowRY` -> vertical brow motion
- `ParamBrowLAngle` / `ParamBrowRAngle` -> brow angle

### Hair
Physics output parameters bind to rotation intent:
- `ParamHairFrontX`
- `ParamHairSideLX`
- `ParamHairSideRX`
- `ParamHairBackX`

P2-R6 will generate the spring chains that drive these parameters.

## Morph intents

P2-R3 specifies semantic intent, not concrete vertex deltas.

Examples:
```text
eye_close_y
mouth_open_y
mouth_form_x
brow_translate_y
brow_rotate
body_breath_scale_y
```

Each intent contains target part, parameter ID, key values, semantic operation, amplitude and amplitude unit.
P2-R5 turns these intents into actual mesh keyform deltas.

## Determinism

For equal semantic content, output must not depend on layer input order or landmark input order.
Duplicate landmark IDs are rejected instead of being resolved by input order.

## R3 exit criteria
- deterministic pivot resolution
- canonical deformer hierarchy
- R8B tracking parameter coverage
- morph intent generation
- optional hair pruning
- fallback QA findings
- zero renderer dependencies
- P2-R1/R2/R3 regression suite passes
