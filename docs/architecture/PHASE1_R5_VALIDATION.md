# Phase 1 R5 Validation

Status: **PASS**

## Determinism
- 30 FPS: PASS
- 60 FPS: PASS
- 120 FPS: PASS
- max final cross-rate difference: `0`
- required tolerance: `1e-3`

## Golden parity
Actual compiled TypeScript implementation vs canonical golden:
- max error: `0`

## Stability
60-second changing-input run:
- NaN: none
- Inf: none
- invalid chain reset failure: none
- output remained inside declared parameter bounds

## Schema
R5 golden model validated against Avatar IR Draft 2020-12 schema:
- errors: `0`

## Performance smoke benchmark
100 spring chains, 5 nodes each, four constraint iterations:
- about `87.14 us` / physics frame in Node.js v22.16.0

## Result
R5 is accepted for Phase 1.

The TypeScript implementation is now the reference oracle for a future Rust/WASM port.
