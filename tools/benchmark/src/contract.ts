export interface BenchmarkCase {
  id: string;
  vertices: number;
  parts: number;
  parameters: number;
  physicsChains: number;
  influencesPerVertex: number;
  warmupFrames: number;
  sampleFrames: number;
}

export const PERFORMANCE_CONTRACT = {
  standardAvatar: {
    maxVisibleParts: 100,
    maxVertices: 50_000,
    maxParameters: 256,
    maxPhysicsChains: 100,
    maxAtlasDimension: 4096,
    maxAtlases: 4
  },
  desktop1080p: {
    releaseGateFps: 60,
    targetFps: 120,
    targetMainThreadMsP95: 2.0,
    targetPhysicsMsP95: 1.0,
    targetGpuMsP95: 5.0
  },
  requiredPercentiles: ["p50", "p95", "p99"] as const
} as const;

const base = {
  influencesPerVertex: 4,
  warmupFrames: 180,
  sampleFrames: 600
};

export const BENCHMARK_MATRIX: readonly BenchmarkCase[] = [
  { ...base, id: "vertices-10k", vertices: 10_000, parts: 50, parameters: 128, physicsChains: 25 },
  { ...base, id: "baseline-25k", vertices: 25_000, parts: 50, parameters: 128, physicsChains: 25 },
  { ...base, id: "vertices-50k", vertices: 50_000, parts: 50, parameters: 128, physicsChains: 25 },
  { ...base, id: "parts-20", vertices: 25_000, parts: 20, parameters: 128, physicsChains: 25 },
  { ...base, id: "parts-100", vertices: 25_000, parts: 100, parameters: 128, physicsChains: 25 },
  { ...base, id: "parameters-64", vertices: 25_000, parts: 50, parameters: 64, physicsChains: 25 },
  { ...base, id: "parameters-256", vertices: 25_000, parts: 50, parameters: 256, physicsChains: 25 },
  { ...base, id: "physics-0", vertices: 25_000, parts: 50, parameters: 128, physicsChains: 0 },
  { ...base, id: "physics-100", vertices: 25_000, parts: 50, parameters: 128, physicsChains: 100 },
  { ...base, id: "stress-50k-100p", vertices: 50_000, parts: 100, parameters: 256, physicsChains: 100 }
];
