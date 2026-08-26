# Phase 1 — Runtime tasks

Order is intentional.

## R1 — Package loader
- parse `.a2d` ZIP
- validate manifest/model
- create typed buffer views
- reject malformed offsets/alignment

## R2 — Parameter core
- fixed parameter index table
- Float32Array storage
- clamp/default/reset
- dirty range

## R3 — WebGL2 reference renderer
- atlas textures
- immutable draw list
- one-time topology upload
- no per-frame sorting
- no per-frame mesh allocation

## R4 — GPU morph/deformer prototype
- morph
- rotation
- pseudo3d_head
- warp after data layout is proven

## R5 — Physics
- spring chain
- fixed timestep option
- deterministic test vectors

## R6 — WebGPU backend
- same Runtime API
- shared benchmark scene

## R7 — Benchmark gate
- 10k / 25k / 50k vertices
- 20 / 50 / 100 parts
- 60 / 120 FPS
- p50/p95/p99 frame time
- draw calls
- CPU/physics/GPU timings

## R8 — Golden model
One manually authored model proving:
- head XYZ
- blink
- iris
- mouth
- hair physics
