# Phase 1 status — R1/R2/R3

## R1 Package Loader — IMPLEMENTED
- reads `.a2d` ZIP through an abstract ZipReader
- validates manifest version
- validates model version
- validates duplicate IDs
- validates parameter defaults
- validates buffer references
- validates 4-byte buffer-view alignment
- validates binary byte lengths
- exposes zero-copy typed views where alignment permits

## R2 Parameter Core — IMPLEMENTED
- fixed parameter index table
- Float32Array state
- min/max clamp
- reset to defaults
- dirty-range tracking
- no per-frame object rebuild required

## R3 WebGL2 Reference Renderer — IMPLEMENTED
- immutable draw list built at load
- one-time topology upload
- positions/UV/index buffers split explicitly
- Uint16 and Uint32 indices supported
- no per-frame sort
- no per-frame vertex upload
- reference shader includes a temporary ParamAngleX deformation only to prove parameter-to-GPU flow

## Not yet production-ready
- texture atlas sampling
- clipping masks
- real morph buffers
- real `pseudo3d_head`
- warp deformer
- physics
- WebGPU backend
- formal p50/p95/p99 benchmark harness

Next gate: R4 GPU deformation data layout.
