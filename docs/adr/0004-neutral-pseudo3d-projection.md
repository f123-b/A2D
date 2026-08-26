# ADR-0004: Preserve the authored neutral pose in Pseudo3D projection

Status: Accepted

## Context

The original R4 projection used absolute proxy depth in the perspective divisor. As a result, vertices with non-zero `proxyZ` were scaled even when `ParamAngleX = ParamAngleY = 0`. The neutral runtime pose therefore did not reproduce the authored 2D mesh.

## Decision

Perspective uses **depth change relative to neutral proxy depth**:

```text
depthDelta = rotatedDepth - neutralProxyDepth
scale = 1 / max(0.25, 1 + perspective * depthDelta)
```

At zero yaw/pitch, `depthDelta = 0`, so the projection is exactly identity before roll/morph.

## Consequences

- CPU reference, WebGL2 GLSL and WebGPU WGSL must use the same equation.
- R4 golden deformation vectors are regenerated.
- Existing `.a2d` files remain binary/schema compatible; this is a runtime semantic correction, not a format change.
