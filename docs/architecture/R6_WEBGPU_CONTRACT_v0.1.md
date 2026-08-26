# R6 WebGPU Contract v0.1

Status: **IMPLEMENTED ON FEATURE BRANCH — HARDWARE VALIDATION REQUIRED**

## Decision

WebGPU is the primary high-performance renderer. WebGL2 remains the compatibility fallback.

The `.a2d` / Avatar IR format is unchanged by R6.

## Data flow

```text
Avatar IR
   |
   +-- static mesh views --------------------> GPU vertex/index buffers
   +-- 16-byte morph influence records ------> one-time vec4<f32> repack
   +-- parameter definitions ----------------> storage buffer
   +-- pseudo3d head metadata ---------------> uniform buffer
   |
ParameterCore dirty range
   |
   +------------------------------------------> queue.writeBuffer(parameter range)
                                                   |
                                                   v
                                             WGSL vertex stage
                                                   |
                              morph -> pseudo3d -> roll -> render
```

## Why one-time repack is allowed

Avatar IR uses a compact mixed 16-byte morph record:

```text
u32 parameterIndex
f32 deltaX
f32 deltaY
f32 weight
```

WGSL storage-struct alignment would enlarge a direct typed struct. R6 therefore repacks each record once at load into `vec4<f32>`:

```text
x = exact parameter index (v1 <= 256, exactly representable)
y = deltaX
z = deltaY
w = weight
```

This keeps the file format backend-neutral and avoids per-frame conversion.

## Dynamic uploads

Only `ParameterCore.consumeDirtyRange()` is uploaded each frame:

```text
byteOffset = start * 4
size       = (endExclusive - start) * 4
```

No vertex position upload occurs during normal animation.

## WebGPU resources

Per avatar:
- parameter state storage buffer
- parameter definition storage buffer
- morph influence storage buffer
- pseudo3d head uniform buffer

Per part:
- position vertex buffer
- UV vertex buffer
- proxy-Z vertex buffer
- influence-range integer vertex buffer
- index buffer

## Shader parity

WGSL follows the R4 CPU reference order:

```text
base
-> morph accumulation
-> pseudo3d yaw/pitch
-> roll
-> clip space
```

Current v1 backend cap remains **8 morph influences per vertex**, matching WebGL2 R4. The Avatar IR does not inherit this limit.

## Backend selection

Default:

```text
WebGPU available + initialization succeeds -> WebGPU
otherwise                                -> WebGL2
```

Studio query overrides:
- `?backend=webgpu` requires WebGPU and disables fallback
- `?backend=webgl2` forces WebGL2

## R6 merge gate

Before merging to `main`:
1. strict TypeScript check passes
2. CPU/layout tests pass
3. real Chromium/Edge WebGPU shader compilation succeeds
4. `r5-golden.a2d` visually renders on WebGPU
5. WebGPU/WebGL2 golden parameter positions agree within `1e-4`
6. no validation errors in browser console
7. 10k/25k/50k benchmark data captured for R7

## Current validation limitation

The development execution container has Chromium installed, but its GPU process cannot initialize EGL/XCB. Therefore no claim of real WebGPU execution or performance is made from this environment. Hardware/browser validation remains an explicit PR merge gate.
