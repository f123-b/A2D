# Phase 2 R4 — Proxy-Z Head Compiler Contract v0.1

## Goal

Compile a face mesh and semantic rig into renderer-independent pseudo-depth that is consumed by the existing Runtime `pseudo3d_head` path.

```text
face layer + face mesh + semantic rig + landmarks
        ↓
profile center / radius estimation
        ↓
ellipsoid base depth
        ↓
semantic landmark depth biases
        ↓
topology-aware smoothing
        ↓
proxyZ f32 buffer + Pseudo3DHeadData
```

## Coordinate contract

- mesh positions, pivots, landmarks and radius are normalized canvas coordinates.
- `proxy_z` is dimensionless pseudo-depth.
- `depth_scale` converts dimensionless proxy depth into normalized-canvas depth.
- the compiler never performs rendering and never depends on WebGPU/WebGL2.

## Base profile

For each face vertex:

```text
dx = (x - profileCenter.x) / radius.x
dy = (y - profileCenter.y) / radius.y
r² = dx² + dy²
zBase = max(0, 1 - r²)^radialExponent
```

The default radial exponent is `0.65`. The silhouette approaches zero depth while central face vertices remain forward.

## Radius estimation

- base radius = `0.5 × face bbox width/height`.
- if both eye-center landmarks are available at confidence >= 0.5, x-radius is refined from inter-eye distance and clamped to `[0.44, 0.60] × face bbox width`.
- y-radius remains bbox-derived in v0.1.

## Semantic depth features

Landmark-local Gaussian depth biases are deterministic and ordered:

| Feature | Bias | Purpose |
|---|---:|---|
| nose | +0.24 | strongest forward feature |
| cheek L/R | +0.07 | preserve cheek volume |
| eye L/R | +0.035 | small orbital lift |
| mouth | +0.025 | retain mouth plane |
| ear L/R | -0.10 | push lateral ears backward |

Missing optional feature landmarks do not fail compilation. Missing nose emits `proxy-z-nose-fallback` because the base ellipsoid is used without a central semantic correction.

## Hair depth metadata

P2-R4 also emits part-level depth bias rules for future whole-head compilation:

- `hair_front`: +0.18
- `hair_side_l/r`: +0.03
- `hair_back`: -0.20

These values are metadata in R4; P2-R5/P2-R8 may use them when compiling per-part proxy depth.

## Smoothing

- adjacency is derived only from the face mesh triangles.
- boundary vertices are frozen to protect the silhouette.
- interior values use deterministic Laplacian smoothing.
- default: 2 iterations, strength 0.28.

## Runtime compatibility

The compiler mirrors the Phase-1 reference projection exactly:

```text
z0 = proxyZ * depthScale
rotate yaw/pitch
depthDelta = rotatedZ - z0
perspectiveScale = 1 / max(0.25, 1 + perspective * depthDelta)
```

The relative-depth term is mandatory: `AngleX=0` and `AngleY=0` must preserve the original authored 2D vertex exactly.

Default runtime data:

- `depthScale = min(radius) × 0.55`
- `perspective = 1.10`
- `yawGain = 1.0`
- `pitchGain = 1.0`

## Binary layout

`pack_proxy_z_buffer()` emits contiguous little-endian `f32` values, one scalar per face mesh vertex, ready for an Avatar IR `BufferView`.

## Determinism

Equivalent semantic input, mesh topology and landmarks must produce byte-equivalent packed Proxy-Z values regardless of landmark input order.

## R4 gates

- neutral projection identity
- yaw +30° / -30° golden
- pitch +20° / -20° golden
- face center depth > silhouette depth
- nose landmark increases local forward depth
- eye-pair radius refinement
- part depth bias metadata
- invalid mesh index rejection
- little-endian f32 packing
