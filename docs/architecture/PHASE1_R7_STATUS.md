# Phase 1 — R7 Status

Status: **HARNESS IMPLEMENTED / HARDWARE DATA PENDING**

## Implemented
- stacked Git branch from R6
- synthetic Avatar IR generator
- exact 10k/25k/50k vertex workloads
- 20/50/100 part workloads
- 64/128/256 parameter workloads
- 0/25/100 spring-chain workloads
- 4 morph influences per vertex
- 1920x1080 physical-pixel target
- WebGPU / WebGL2 selectable runner
- p50/p95/p99 statistics
- refresh-rate detection
- release/target gate evaluator
- JSON copy/download
- static GPU byte estimate
- regression comparison CLI
- synthetic generator structural tests

## Not yet claimed
No real WebGPU/WebGL2 performance numbers are committed yet.

The current execution environment cannot provide a trustworthy target GPU result.

## Next hardware run
Use the same machine/browser build for both:
1. WebGPU full matrix
2. WebGL2 full matrix
3. save JSON reports
4. compare the baseline case and stress case
5. use results to choose the next optimization

## Likely optimization order after measurement
1. draw-call pressure / batching
2. parameter dirty-range behavior
3. influence fetch layout
4. shader arithmetic
5. timestamp-query GPU profiling
6. atlas / clipping benchmark extension
