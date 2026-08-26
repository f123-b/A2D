# R7 Benchmark Contract v0.1

Status: **IMPLEMENTED FOR SYNTHETIC RUNTIME BENCHMARKING**

## Purpose

R7 turns "fast" into a repeatable regression contract.

The first benchmark suite measures the deformation/runtime core only. It deliberately excludes:
- ZIP/package parsing
- AI decomposition
- texture atlas sampling
- clipping masks
- art-dependent overdraw
- tracking model inference

Those are separate benchmark layers.

## Standard matrix

R7 uses a curated matrix instead of the full Cartesian product.

| Case | Vertices | Parts | Parameters | Physics chains |
|---|---:|---:|---:|---:|
| vertices-10k | 10k | 50 | 128 | 25 |
| baseline-25k | 25k | 50 | 128 | 25 |
| vertices-50k | 50k | 50 | 128 | 25 |
| parts-20 | 25k | 20 | 128 | 25 |
| parts-100 | 25k | 100 | 128 | 25 |
| parameters-64 | 25k | 50 | 64 | 25 |
| parameters-256 | 25k | 50 | 256 | 25 |
| physics-0 | 25k | 50 | 128 | 0 |
| physics-100 | 25k | 50 | 128 | 100 |
| stress-50k-100p | 50k | 100 | 256 | 100 |

Default morph density:
- 4 influences / vertex
- runtime backend cap remains 8 / vertex

## Resolution

Benchmark target is physical **1920 x 1080** pixels.

CSS canvas dimensions are adjusted by devicePixelRatio so the renderer's DPR scaling resolves back to 1920 x 1080 physical pixels.

## Sampling

Per case:
- 90 RAF frames for refresh-rate calibration
- 180 warmup frames
- 600 measured frames

Warmup is excluded from reported percentiles.

## Dynamic workload

Every measured frame:
1. all avatar parameters receive deterministic sinusoidal input
2. fixed-step physics runs
3. physics writes outputs back to ParameterCore
4. renderer consumes the dirty range
5. one render is submitted

This intentionally exercises the worst case of a full parameter-range update.

## Metrics

Required:
- frame interval p50 / p95 / p99
- CPU render-submit p50 / p95 / p99
- physics p50 / p95 / p99
- draw calls
- estimated static GPU memory
- full parameter upload bytes
- estimated display refresh rate

Future:
- WebGPU timestamp-query GPU p50/p95/p99
- WebGL2 disjoint timer query
- texture/atlas bytes
- clipping-mask passes
- overdraw

## Interpretation

`frameMs` comes from requestAnimationFrame and is display-refresh limited.

It can answer:
- can the full runtime sustain a display cadence?

It cannot by itself answer:
- what is raw GPU execution time?

`submitCpuMs` measures CPU-side render submission only.

## Gate logic

Desktop 1080p:
- release 60 Hz assessable only when detected refresh >= 58 Hz
- release frame p95 target <= 17.5 ms
- target 120 Hz assessable only when detected refresh >= 115 Hz
- target frame p95 <= 8.75 ms
- render submit CPU p95 <= 2.0 ms
- physics p95 <= 1.0 ms

GPU p95 <= 5 ms becomes enforceable when timestamp-query instrumentation is added.

## Regression comparison

Benchmark reports use schemaVersion 1.

The CLI comparator matches:
`backend + case.id`

and checks:
- frame p95
- submit p95
- physics p95

Default allowed regression:
8%.

## R7 exit gate

R7 infrastructure is code-complete when:
- synthetic package generator is deterministic
- exact requested vertices/parts/parameters/physics are tested
- WebGPU and WebGL2 use the same generated Avatar IR
- metrics are exportable as JSON
- regression comparator exists
- CI builds and tests the harness

R7 performance data is hardware-complete only after both backends are run on the same target machine.
