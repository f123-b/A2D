# Phase 1 — R8A Status

## R8A-1 Resource/Compositing Foundation
Status: **IMPLEMENTED / GPU BACKEND INTEGRATION NEXT**

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

Tests added for:
- premultiplied source-over
- multi-source mask union
- raw RGBA8 premultiplication
- render plan texture resolution
- self-mask rejection
- unknown texture rejection
- loader asset loading
- path traversal rejection

## R8A-2 Next
Connect the frozen visual contract to both GPU backends and add visual golden validation.
