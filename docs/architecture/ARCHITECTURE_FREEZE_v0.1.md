# A2D Architecture Freeze v0.1

Status: **FROZEN FOR PHASE 1**

## 1. Product boundary

A2D Studio is not a Cubism clone. The product owns:

- image/layer ingest
- semantic normalization
- automatic rig compilation
- Avatar IR
- runtime
- tracking adapters
- editor
- QA
- exporters

Cubism/nijilive compatibility is downstream and must not leak into the core model.

## 2. Primary pipeline

```text
PNG/JPG/PSD
    |
    v
Decomposer
    |
    v
Semantic Layers
    |
    v
Rig Compiler
  - landmarks
  - adaptive mesh
  - anchors
  - deformers
  - physics
  - expressions
  - QA
    |
    v
A2D Avatar IR
    |
    +--> Runtime
    +--> Pro Editor
    +--> Exporters
```

## 3. Runtime split

CPU/WASM:
- tracking normalization
- parameter smoothing
- animation state
- physics integration
- dirty-range calculation

GPU:
- morph accumulation
- deformer evaluation
- pseudo-3D projection
- clipping
- final mesh transform
- rendering

Forbidden hot-path behavior:
- rebuilding topology every frame
- recreating draw lists every frame
- sorting immutable draw order every frame
- uploading every vertex every frame
- allocating large transient JS objects every frame

## 4. `.a2d` container

`.a2d` is a ZIP container.

Required:
- `manifest.json`
- `model.json`
- `buffers/geometry.bin`

Optional:
- `buffers/deform.bin`
- `textures/atlas_0.webp`
- `textures/atlas_1.webp`
- `motions/*.json`
- `expressions/*.json`
- `metadata/source.json`
- `qa/report.json`

Binary data is little-endian and 4-byte aligned.

JSON contains graph/metadata only. Large vertex/morph arrays are binary buffer views.

## 5. Standard parameter IDs v1

Head:
- ParamAngleX [-30, 30]
- ParamAngleY [-30, 30]
- ParamAngleZ [-30, 30]

Body:
- ParamBodyAngleX [-20, 20]
- ParamBodyAngleY [-20, 20]
- ParamBodyAngleZ [-20, 20]
- ParamBreath [0, 1]

Eyes:
- ParamEyeLOpen [0, 1]
- ParamEyeROpen [0, 1]
- ParamEyeBallX [-1, 1]
- ParamEyeBallY [-1, 1]

Mouth:
- ParamMouthOpenY [0, 1]
- ParamMouthForm [-1, 1]

Brows:
- ParamBrowLY [-1, 1]
- ParamBrowRY [-1, 1]
- ParamBrowLAngle [-1, 1]
- ParamBrowRAngle [-1, 1]

## 6. Deformer types v1

Only four core types are allowed in v1:

1. `warp`
2. `rotation`
3. `morph`
4. `pseudo3d_head`

Anything else is Phase 2+ unless an ADR changes this freeze.

## 7. Mesh policy

Default generation:
alpha mask -> contour -> feature points -> adaptive sampling -> triangulation

Density priorities:
1. eyes / mouth / chin
2. face contour / hair roots
3. limbs
4. large cloth interior

No fixed-density grid as the universal default.

## 8. Runtime performance contract

Standard Avatar:
- <= 100 visible parts
- <= 50,000 vertices total
- <= 256 parameters
- <= 100 physics chains
- <= 4096 atlas texture dimension per atlas
- <= 4 atlases

Desktop target at 1920x1080:
- 60 FPS: release gate
- 120 FPS: performance target on capable desktop GPU
- JS main-thread runtime work: target < 2 ms/frame
- physics: target < 1 ms/frame
- GPU render/deform: target < 5 ms/frame

Benchmark must report p50/p95/p99 frame time, not only average FPS.

## 9. Product UX contract

Simple mode:
upload -> generate -> auto QA -> live preview -> camera/mic -> export

Simple mode must not expose:
- vertices
- deformers
- z/depth
- physics constants
- parameter keyforms

Pro mode may expose those.

## 10. Phase 1 exit criteria

Before building the full editor, Phase 1 must prove:

- load `.a2d`
- parameter update
- head XYZ
- eye blink
- iris
- mouth
- simple hair physics
- 1080p stable 60 FPS
- benchmark harness with p95 frame time
