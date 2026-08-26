# Phase 1 — R8A Status

## R8A-1 Resource/Compositing Foundation
Status: **PASS**

Implemented:
- TextureResourceV1 in Avatar IR
- package texture asset loading
- safe package-relative URI validation
- raw RGBA8 exact-size validation
- PNG/WebP decode contract
- canonical premultiplied-alpha conversion
- Part material binding and opacity
- inside/outside clipping schema
- multi-source soft alpha-union reference
- immutable VisualRenderPlan compiler
- deterministic draw-order tie break
- clip source validation
- legacy textureAtlas compatibility

## R8A-2 GPU Visual Runtime
Status: **PASS CODE / HARDWARE VISUAL VALIDATION PENDING**

Implemented:
- async texture decode during backend creation
- opaque-white fallback for legacy textureless models
- WebGPU/WebGL2 texture upload and sampling
- premultiplied source-over blend in both backends
- one soft RGBA8 mask target per unique clip key
- multi-source alpha-union by GPU blending
- inside/outside clip sampling
- mask targets recreated only on resize
- GPU timer scope includes mask + main passes
- CPU visual golden math

## R8A-3 Visual Golden + Profiling
Status: **IMPLEMENTED / HARDWARE DATA PENDING**

Implemented:
- deterministic packaged visual Golden `.a2d`
- 9-part stylized avatar fixture
- one atlas texture
- left/right eye-white -> iris clipping
- pseudo3d head parameters
- physics-driven front-hair morph
- artifact SHA-256 integrity test
- six visual benchmark cases
- texture/mask/overdraw workload generation
- visual memory/draw-cost estimates in benchmark output
- 4/16/32-mask stress cases

Next gate:
- run real WebGPU/WebGL2 visual benchmark reports
- capture golden-model screenshots on both backends
- decide whether v1 full-frame mask targets need immediate mask-atlas optimization
