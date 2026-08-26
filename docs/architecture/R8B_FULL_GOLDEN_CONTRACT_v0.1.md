# R8B Full Golden Avatar Contract v0.1

Status: **IMPLEMENTED / PHASE-1 GOLDEN TARGET**

## Purpose

The deterministic R8B fixture is the canonical semantic target that Phase 2 Auto Rig Compiler must be able to generate from normalized semantic layers.

It is deliberately small in geometry but complete in runtime semantics. The source of truth is `createR8BFullGoldenPackage()`; `buildR8BFullGoldenA2D()` emits real `.a2d` package bytes and tests load those bytes through the production loader.

## Required standard parameters

- Head: `ParamAngleX/Y/Z`
- Body: `ParamBodyAngleX/Y/Z`
- Breath: `ParamBreath`
- Eyes: `ParamEyeLOpen`, `ParamEyeROpen`, `ParamEyeBallX/Y`
- Mouth: `ParamMouthOpenY`, `ParamMouthForm`
- Brows: `ParamBrowLY/RY`, `ParamBrowLAngle/RAngle`

Golden physics outputs:
- `ParamHairFrontX`
- `ParamHairSideLX`
- `ParamHairSideRX`
- `ParamHairBackX`

## Part hierarchy

```text
body
├── cloth
├── hair-back
└── face
    ├── brow-l
    ├── brow-r
    ├── eye-white-l
    │   └── iris-l
    ├── eye-white-r
    │   └── iris-r
    ├── mouth
    ├── hair-side-l
    ├── hair-side-r
    └── hair-front
```

The loader rejects missing parents, empty parent IDs, self-parenting and hierarchy cycles.

## Expression Preset v1

Expressions are named parameter overlays.

Binding modes:
- `set`: blend current parameter toward an absolute value
- `add`: add a weighted offset

Runtime frame order:

```text
tracking
  -> animation
  -> expression
  -> physics
  -> dirty parameter upload
  -> GPU deformation/render
```

Golden presets:
- `happy`
- `surprised`
- `angry`

## Physics

Four deterministic 120 Hz spring chains:
- front hair
- left side hair
- right side hair
- back hair

## Visual contract

- one RGBA8 atlas resource
- premultiplied runtime compositing
- left/right eye white used as independent soft masks
- irises clipped inside their corresponding eye whites
- deterministic draw order

## Phase-1 acceptance represented by the Golden

The fixture exercises:
- texture asset loading
- part hierarchy
- head XYZ
- body XYZ morphs
- breath
- independent blink
- gaze XY
- mouth open/form
- brow position/angle
- four hair physics outputs
- expression presets
- soft clipping
- production `.a2d` packaging/loading
- WebGPU/WebGL2 visual runtime compatibility

Actual hardware parity/performance remains a separate hardware gate.
