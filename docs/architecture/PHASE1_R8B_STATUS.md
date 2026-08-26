# Phase 1 — R8B Status

Status: **IMPLEMENTED / CI PENDING**

## Full Golden Avatar

R8B uses a deterministic TypeScript fixture factory rather than a hand-maintained binary artifact as the source of truth.

Factory:
- `packages/runtime-api/src/fullGoldenFixture.ts`
- `createR8BFullGoldenPackage()` builds the in-memory Avatar IR and assets
- `buildR8BFullGoldenA2D()` emits real `.a2d` ZIP bytes
- the contract test loads those bytes again through the production ZIP reader and package loader

Current Golden contract:
- 14 parts
- 21 parameters
- 4 spring physics chains
- 3 expression presets
- 84 morph influence records
- 1 RGBA8 atlas
- 2 independent iris clipping groups

## Runtime additions

Expression Preset v1:
- `set`
- `add`
- weighted application

Loader semantic validation:
- missing parent rejection
- self-parent rejection
- hierarchy cycle rejection
- duplicate expression rejection
- missing expression parameter rejection
- absolute expression target range validation

## Capability target

- head XYZ
- body XYZ
- breath
- independent blink
- gaze XY
- mouth open/form
- brow Y/angle
- front/left-side/right-side/back hair physics
- texture atlas
- premultiplied compositing
- soft eye clipping
- happy/surprised/angry presets

## Phase-1 gate after CI

Once CI is green, Phase 1 is code-complete except for the already-declared real-hardware WebGPU/WebGL2 visual parity and performance gate.

Phase 2 then starts from:

`normalized semantic layers -> landmarks -> adaptive mesh -> semantic rig -> R8B-equivalent Avatar IR`.
