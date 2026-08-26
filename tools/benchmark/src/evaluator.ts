import { PERFORMANCE_CONTRACT } from "./contract.js";
import type { BenchmarkResult } from "./runner.js";

export interface GateEvaluation {
  release60Hz: "pass" | "fail" | "not-assessable";
  target120Hz: "pass" | "fail" | "not-assessable";
  mainThreadP95: "pass" | "fail";
  physicsP95: "pass" | "fail";
}

export function evaluate(result: BenchmarkResult): GateEvaluation {
  const refresh = result.environment.estimatedRefreshHz;
  const release60Hz = refresh !== null && refresh >= 58
    ? (result.frameMs.p95 <= 17.5 ? "pass" : "fail")
    : "not-assessable";
  const target120Hz = refresh !== null && refresh >= 115
    ? (result.frameMs.p95 <= 8.75 ? "pass" : "fail")
    : "not-assessable";

  return {
    release60Hz,
    target120Hz,
    mainThreadP95: result.submitCpuMs.p95 <= PERFORMANCE_CONTRACT.desktop1080p.targetMainThreadMsP95 ? "pass" : "fail",
    physicsP95: result.physicsMs.p95 <= PERFORMANCE_CONTRACT.desktop1080p.targetPhysicsMsP95 ? "pass" : "fail"
  };
}
