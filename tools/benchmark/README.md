# A2D R7 Benchmark

Browser benchmark harness for the A2D deformation/runtime core.

## Run

```bash
pnpm install
pnpm --filter @a2d/benchmark dev
```

Open the local page and run the same case on WebGPU and WebGL2.

The runner generates synthetic Avatar IR packages in memory, so disk/ZIP parsing is excluded from the render benchmark.

## Matrix

The standard matrix isolates:
- vertex scaling: 10k / 25k / 50k
- draw-call scaling: 20 / 50 / 100 parts
- parameter scaling: 64 / 128 / 256
- physics scaling: 0 / 25 / 100 spring chains
- integrated stress: 50k vertices / 100 parts / 256 parameters / 100 chains

Every synthetic vertex has four morph influences by default.

## Metrics

- RAF frame interval p50/p95/p99
- render submit CPU p50/p95/p99
- physics p50/p95/p99
- draw calls
- estimated static GPU bytes
- parameter upload bytes
- detected display refresh rate

`frameMs` is display-refresh limited. `submitCpuMs` is CPU submission time and does not claim GPU completion time.

## Compare reports

```bash
pnpm --filter @a2d/benchmark compare baseline.json candidate.json --max-regression=0.08
```

The command exits non-zero when a matched case regresses beyond the allowed ratio.
