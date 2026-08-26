const CONTRACT = {
  standardAvatar: {
    maxVisibleParts: 100,
    maxVertices: 50000,
    maxParameters: 256,
    maxPhysicsChains: 100,
    maxAtlasDimension: 4096,
    maxAtlases: 4
  },
  desktop1080p: {
    releaseGateFps: 60,
    targetFps: 120,
    targetMainThreadMs: 2.0,
    targetPhysicsMs: 1.0,
    targetGpuMs: 5.0
  },
  requiredPercentiles: ["p50", "p95", "p99"]
};

console.log(JSON.stringify(CONTRACT, null, 2));
