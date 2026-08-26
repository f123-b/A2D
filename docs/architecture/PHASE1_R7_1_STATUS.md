# Phase 1 — R7.1 Status

Status: **GPU PROFILING CODE COMPLETE / HARDWARE DATA PENDING**

## Implemented

- shared optional GPU timing Runtime interface
- profiling disabled by default
- WebGPU `timestamp-query` feature negotiation
- WebGPU pass timestamps
- 8-slot asynchronous WebGPU query/readback ring
- WebGL2 `EXT_disjoint_timer_query_webgl2`
- WebGL2 asynchronous availability polling
- WebGL2 disjoint-result rejection
- GPU p50 / p95 / p99 in R7 report
- GPU sample count and coverage
- GPU p95 <= 5 ms gate
- `not-assessable` behavior when native timers are unavailable
- GPU p95 regression comparison when both reports contain it
- evaluator regression tests

## Local validation

- Runtime changed files: TypeScript 5.8.3 strict PASS using dependency-compatible stubs
- Benchmark changed files: TypeScript 5.8.3 strict PASS
- Benchmark tests: 8/8 PASS

## Hardware validation pending

No GPU timing number is claimed from the current execution environment. The first accepted baseline must come from a machine where both selected backend APIs can create their native timer queries.
