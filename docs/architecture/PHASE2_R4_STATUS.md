# Phase 2 R4 Status — Proxy-Z Head Compiler

Status: **code complete / local reference validation complete**

## Delivered

- deterministic ellipsoid face depth profile
- profile center and head radius estimation
- eye-pair x-radius refinement
- nose/cheek/eye/mouth/ear Gaussian depth features
- topology-aware interior smoothing with frozen boundary
- hair front/side/back depth-bias metadata
- Runtime-compatible `Pseudo3DHeadDataV1`
- little-endian Proxy-Z f32 buffer packing
- Python projection mirror of the Phase-1 Runtime reference

## Validation

New P2-R4 tests:

```text
9 / 9 PASS
```

Reference projection golden:

```text
pivot       = (0.50, 0.44)
depthScale  = 0.11
perspective = 1.10
point        = (0.60, 0.44), proxyZ=0.8

yaw +30° x  = 0.6401267813
yaw -30° x  = 0.5408841290

point        = (0.50, 0.52), proxyZ=0.8
pitch +20° y = 0.4840099547
pitch -20° y = 0.5491972427
```

Neutral yaw/pitch returns the exact input 2D position.

## Deferred

- full head-part proxyZ emission for hair/ears/accessories
- learned monocular depth
- asymmetric face-depth model from pose-estimation confidence
- constrained mesh/depth joint optimization
- hardware screenshot parity remains the Phase-1 hardware gate

## Next

P2-R5 — Facial Morph Compiler: turn Semantic Rig `MorphIntent` values plus real mesh topology/landmarks into bounded per-vertex morph influence records for blink, gaze support, mouth open/form, brows and breath.
