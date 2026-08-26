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
Status: **IMPLEMENTED / HARDWARE VISUAL VALIDATION PENDING**

Implemented:
- async texture decode during backend creation
- opaque-white fallback for legacy textureless models
- WebGPU texture/sampler upload
- WebGL2 texture upload
- premultiplied source-over blend in both backends
- one soft RGBA8 mask target per unique clip key
- multi-source alpha-union by GPU blending
- inside/outside clip sampling in framebuffer space
- mask targets recreated only on resize
- GPU timer scope includes mask + main passes
- CPU visual golden test

Next gate:
- real GPU/browser visual smoke
- eye-white -> iris clipping screenshot
- WebGPU/WebGL2 screenshot parity
- mask/overdraw benchmark extension
