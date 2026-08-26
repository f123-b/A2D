# A2D R7 Benchmark

Browser benchmark harness for the A2D deformation/runtime core.

## Run

```bash
pnpm install
pnpm --filter @a2d/benchmark dev
```

Run the same case on WebGPU and WebGL2. Synthetic Avatar IR is generated in memory so ZIP/disk parsing is excluded.

## Matrix

The standard matrix isolates 10k/25k/50k vertices, 20/50/100 parts, 64/128/256 parameters, 0/25/100 physics chains and an integrated 50k/100-part/256-parameter/100-chain stress case. Every synthetic vertex has four morph influences by default.

## Metrics

- RAF frame p50/p95/p99
- render submit CPU p50/p95/p99
- physics p50/p95/p99
- native GPU p50/p95/p99 when available
- GPU timing sample count / coverage
- draw calls
- estimated static GPU bytes
- parameter upload bytes
- detected display refresh rate

GPU timing sources:

```text
WebGPU -> timestamp-query
WebGL2 -> EXT_disjoint_timer_query_webgl2
```

Profiling is asynchronous and opt-in. The benchmark never uses `gl.finish()` or a per-frame GPU completion wait.

`frameMs` is display-refresh limited, `submitCpuMs` is CPU submission time, and `gpuMs` is native render-pass GPU time when supported.

## Compare reports

```bash
pnpm --filter @a2d/benchmark compare baseline.json candidate.json --max-regression=0.08
```

The command exits non-zero on excessive regression. `gpu.p95` participates when both reports contain native GPU timing.
