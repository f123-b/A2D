# R4 GPU Deformation Contract v0.1

Status: **FROZEN FOR IMPLEMENTATION — amended by ADR-0004**

## Goals
- Editor and Runtime use the same deformation contract.
- WebGL2 and WebGPU consume the same logical buffers.
- Per-frame CPU upload is limited to compact parameter/physics state.
- Mesh topology and static deformation metadata are immutable after load.
- CPU reference evaluator exists for correctness tests.

## Vertex pipeline order
```text
base position
  -> morph accumulation
  -> warp deformer
  -> rotation deformer
  -> pseudo3d_head
  -> parent/world transform
  -> clip-space transform
```

## Static buffers

### BaseVertexBuffer — logical layout, 32 bytes/vertex
```text
0   f32x2 position
8   f32x2 uv
16  f32   proxyZ
20  u32   partIndex
24  u32   influenceOffset
28  u32   influenceCount
```

### MorphInfluenceBuffer — 16 bytes/influence
```text
0   u32 parameterIndex
4   f32 deltaX
8   f32 deltaY
12  f32 weight
```

Contribution:
`position += normalizedParameter * weight * delta`

### Pseudo3DHeadData — 32 bytes
```text
0   f32x2 pivot
8   f32x2 radius
16  f32 depthScale
20  f32 perspective
24  f32 yawGain
28  f32 pitchGain
```

## Dynamic buffer
`ParameterStateBuffer`: one f32 per parameter. Only dirty contiguous ranges are uploaded.

## Parameter normalization
```text
if value >= default:
  n = (value-default)/(max-default)
else:
  n = (value-default)/(default-min)
```
Clamp `n` to `[-1,1]`.

## Pseudo3D head
```text
x0 = x - pivotX
y0 = y - pivotY
z0 = proxyZ * depthScale

yaw   = radians(ParamAngleX * yawGain)
pitch = radians(ParamAngleY * pitchGain)

x1 = cos(yaw)*x0 + sin(yaw)*z0
z1 = -sin(yaw)*x0 + cos(yaw)*z0

y1 = cos(pitch)*y0 - sin(pitch)*z1
z2 = sin(pitch)*y0 + cos(pitch)*z1

depthDelta = z2 - z0
scale = 1 / max(0.25, 1 + perspective*depthDelta)

x2 = x1*scale + pivotX
y2 = y1*scale + pivotY
```

`ParamAngleZ` is applied as 2D roll around the same head pivot.

## Dirty upload contract
1. tracking updates parameters
2. smoothing updates parameters
3. physics updates parameters
4. ParameterCore returns dirty `[start,end)`
5. backend uploads only that range
6. GPU evaluates deformation

Forbidden:
- rebuild influence lists per frame
- rebuild/sort draw order per frame
- upload static mesh metadata per frame
- full vertex upload per frame
- regenerate proxyZ per frame

## Correctness gate
GPU backends must match the CPU reference evaluator within:
`absolute position error <= 1e-4` normalized canvas units.

## R4 exit criteria
- schema supports deformation buffers
- CPU reference evaluator exists
- morph + pseudo3d_head reference paths exist
- golden vectors exist
- WebGL2 can consume the same compact dynamic parameter contract
