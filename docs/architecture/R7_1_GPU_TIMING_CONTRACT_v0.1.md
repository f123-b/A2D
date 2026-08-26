# R7.1 GPU Timing Contract v0.1

Status: **IMPLEMENTED / HARDWARE VALIDATION PENDING**

## Purpose

R7.1 adds backend-native GPU execution timing to the R7 benchmark suite without introducing synchronous GPU stalls.

The profiler is a Runtime backend capability. Benchmark code consumes the same `DeformationRenderer` interface for WebGPU and WebGL2.

## Runtime API

Every deformation renderer exposes:

```ts
readonly gpuTiming: {
  supported: boolean;
  source?: "webgpu-timestamp-query" | "webgl2-disjoint-timer-query";
  reason?: string;
};
setGpuTimingEnabled(enabled: boolean): void;
collectGpuTimings(): Promise<number[]>;
```

Profiling is **disabled by default**, so normal Studio/runtime playback does not pay query/readback cost unless explicitly enabled.

## WebGPU

Capability is negotiated with `adapter.features.has("timestamp-query")`. When present, the device is requested with `requiredFeatures: ["timestamp-query"]`.

Each timed pass writes beginning/end timestamps. Results are resolved to a GPU buffer and asynchronously copied to a MAP_READ buffer through an 8-slot ring. If all slots are in flight, rendering continues and that frame's timing sample is skipped instead of stalling.

Timestamp values are nanoseconds:

```text
gpuMs = (endNs - beginNs) / 1_000_000
```

## WebGL2

Capability is `EXT_disjoint_timer_query_webgl2`.

```text
gl.beginQuery(TIME_ELAPSED_EXT)
clear + uniforms + draws
gl.endQuery(TIME_ELAPSED_EXT)
```

Results are polled on later event-loop turns through `QUERY_RESULT_AVAILABLE`. If `GPU_DISJOINT_EXT` is true, affected pending samples are discarded.

`gl.finish()` is forbidden.

## Measurement scope

`gpuMs` measures the render pass/query interval: clear, deformation shader work and draw calls. CPU parameter generation, physics, package parsing and AI work remain separate metrics.

Parameter upload stays outside the timed render-pass interval in both backends so the two GPU measurements are comparable.

## Sampling and gate

R7 still measures 600 frames. GPU timing is assessable when the backend reports native timing support and at least 30 valid GPU samples are collected.

Reports include `gpuTiming.supported`, `source`, `reason`, `samples`, `coverage` and `gpuMs.p50/p95/p99`.

Desktop 1080p target:

```text
gpuMs.p95 <= 5.0 ms
```

If a native asynchronous timer is unavailable, the GPU gate is `not-assessable`; it is never inferred from RAF or CPU submission time.

## Regression comparator

When baseline and candidate both contain native GPU measurements, `compare.mjs` adds `gpu.p95` to the existing regression checks. Default allowed regression remains 8%.

## Hardware exit gate

1. WebGPU must provide >=30 valid timestamp-query samples on the target machine.
2. WebGL2 must provide >=30 valid disjoint-timer samples on the same machine/browser family.
3. Export `baseline-25k` and `stress-50k-100p` JSON for both backends.
4. Review GPU p95 together with frame, submit and physics p95.
5. Never add a synchronous GPU wait merely to increase timing coverage.
