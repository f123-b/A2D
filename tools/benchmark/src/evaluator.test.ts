import test from "node:test";
import assert from "node:assert/strict";
import { evaluate } from "./evaluator.js";
import type { BenchmarkResult } from "./runner.js";

function distribution(p95: number) {
  return { count: 100, min: 0.1, max: p95, mean: p95 / 2, p50: p95 / 2, p95, p99: p95 };
}
function result(overrides: Partial<BenchmarkResult> = {}): BenchmarkResult {
  return {
    schemaVersion: 1,
    case: { id: "test", vertices: 25000, parts: 50, parameters: 128, physicsChains: 25, influencesPerVertex: 4, warmupFrames: 180, sampleFrames: 600 },
    backend: "webgpu",
    environment: { userAgent: "test", devicePixelRatio: 1, width: 1920, height: 1080, estimatedRefreshHz: 120, timestamp: "2026-08-26T00:00:00.000Z" },
    samples: 600,
    frameMs: distribution(8), submitCpuMs: distribution(1), physicsMs: distribution(0.5), gpuMs: distribution(4),
    gpuTiming: { supported: true, source: "webgpu-timestamp-query", samples: 500, coverage: 500 / 600 },
    drawCalls: 50, staticGpuBytesEstimate: 1, parameterBytesPerFullUpload: 512, notes: [],
    ...overrides
  };
}

test("GPU gate passes below 5 ms p95", () => { assert.equal(evaluate(result()).gpuP95, "pass"); });
test("GPU gate fails above 5 ms p95", () => { assert.equal(evaluate(result({ gpuMs: distribution(5.5) })).gpuP95, "fail"); });
test("GPU gate is not assessable when timer unsupported", () => {
  assert.equal(evaluate(result({ gpuMs: undefined, gpuTiming: { supported: false, reason: "missing feature", samples: 0, coverage: 0 } })).gpuP95, "not-assessable");
});
test("GPU gate is not assessable with too few valid samples", () => {
  assert.equal(evaluate(result({ gpuTiming: { supported: true, source: "webgpu-timestamp-query", samples: 12, coverage: 0.02 } })).gpuP95, "not-assessable");
});
