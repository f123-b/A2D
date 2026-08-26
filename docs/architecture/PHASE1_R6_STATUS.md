# Phase 1 — R6 Status

Status: **CODE COMPLETE / DRAFT PR / GPU VALIDATION PENDING**

## Implemented
- WebGPU adapter/device creation
- high-performance adapter preference
- WebGPU canvas configuration
- storage-buffer parameter state
- storage-buffer parameter definitions
- storage-buffer morph influences
- compact 48-byte head uniform
- static per-part vertex/index buffers
- WGSL morph accumulation
- WGSL pseudo3d yaw/pitch
- WGSL roll
- dirty-range `queue.writeBuffer`
- device-lost handling
- automatic WebGPU -> WebGL2 fallback
- forced backend query modes for parity testing
- testable GPU packing helpers

## Offline validation
- strict TypeScript: PASS
- Studio integration strict TypeScript: PASS
- runtime tests: 12/12 PASS
- WebGPU layout executable packing test: PASS
- no Avatar IR schema change
- R4 neutral-pose defect discovered and corrected through ADR-0004

## Hardware validation
Pending because the execution container cannot initialize a Chromium GPU process (EGL/XCB unavailable).

Do not merge R6 until a real WebGPU browser passes the R6 merge gate.

## Next after R6 validation
R7 benchmark suite:
- 10k / 25k / 50k vertices
- 20 / 50 / 100 parts
- p50 / p95 / p99
- CPU submit time
- GPU time where timestamp queries are supported
- draw calls
- WebGPU vs WebGL2
