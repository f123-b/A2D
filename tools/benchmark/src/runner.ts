import {
  createBestDeformationRenderer,
  createPhysicsFromModel,
  type DeformationRenderer
} from "@a2d/runtime-api";
import type { BenchmarkCase } from "./contract.js";
import { estimateStaticBytes } from "./syntheticAvatar.js";
import { createBenchmarkAvatar, estimateVisualCost, type VisualCostEstimate } from "./visualSyntheticAvatar.js";
import { estimateRefreshHz, summarize, type Distribution } from "./statistics.js";

export interface BenchmarkResult {
  schemaVersion: 1;
  case: BenchmarkCase;
  backend: "webgpu" | "webgl2";
  environment: {
    userAgent: string;
    devicePixelRatio: number;
    width: number;
    height: number;
    estimatedRefreshHz: number | null;
    timestamp: string;
  };
  samples: number;
  frameMs: Distribution;
  submitCpuMs: Distribution;
  physicsMs: Distribution;
  gpuMs?: Distribution;
  gpuTiming: {
    supported: boolean;
    source?: string;
    reason?: string;
    samples: number;
    coverage: number;
  };
  drawCalls: number;
  staticGpuBytesEstimate: number;
  parameterBytesPerFullUpload: number;
  visual?: VisualCostEstimate;
  fallbackReason?: string;
  notes: string[];
}

function nextFrame(): Promise<number> {
  return new Promise(resolve => requestAnimationFrame(resolve));
}

function driveParameters(renderer: DeformationRenderer, frame: number): void {
  const t = frame / 120;
  const defs = renderer.model.parameters;
  for (let index = 0; index < defs.length; index++) {
    const def = defs[index];
    const span = def.max - def.min;
    const normalized = 0.5 + 0.45 * Math.sin(t * 2.1 + index * 0.17);
    renderer.parameters.set(index, def.min + span * normalized);
  }
}

export async function runBenchmarkCase(
  canvas: HTMLCanvasElement,
  config: BenchmarkCase,
  backend: "webgpu" | "webgl2",
  onProgress?: (message: string) => void
): Promise<BenchmarkResult> {
  const pkg = createBenchmarkAvatar(config);
  const dpr = devicePixelRatio || 1;
  canvas.style.width = `${1920 / dpr}px`;
  canvas.style.height = `${1080 / dpr}px`;
  canvas.width = 1920;
  canvas.height = 1080;

  const visual = estimateVisualCost(pkg, 1920, 1080);
  const selection = await createBestDeformationRenderer(canvas, pkg, {
    preferWebGPU: backend === "webgpu",
    requireWebGPU: backend === "webgpu"
  });
  const renderer = selection.renderer;
  if (renderer.backend !== backend) {
    renderer.destroy();
    throw new Error(`requested ${backend}, got ${renderer.backend}`);
  }

  const physics = createPhysicsFromModel(pkg.model, {
    physicsHz: 120,
    maxFrameDt: 0.1,
    maxSubSteps: 12
  });

  const calibration: number[] = [];
  let previous = await nextFrame();
  for (let i = 0; i < 90; i++) {
    const now = await nextFrame();
    calibration.push(now - previous);
    previous = now;
  }

  onProgress?.(`warming ${config.id} on ${backend}`);
  renderer.setGpuTimingEnabled(false);
  for (let frame = 0; frame < config.warmupFrames; frame++) {
    const now = await nextFrame();
    const dt = Math.min(0.1, Math.max(0, (now - previous) / 1000));
    previous = now;
    driveParameters(renderer, frame);
    physics.update(dt, renderer.parameters);
    renderer.render();
  }
  await renderer.collectGpuTimings();

  const frameSamples: number[] = [];
  const submitSamples: number[] = [];
  const physicsSamples: number[] = [];
  let drawCalls = 0;

  renderer.setGpuTimingEnabled(true);
  onProgress?.(`sampling ${config.id} on ${backend}${renderer.gpuTiming.supported ? " + GPU timer" : ""}`);
  for (let frame = 0; frame < config.sampleFrames; frame++) {
    const now = await nextFrame();
    const frameMs = now - previous;
    const dt = Math.min(0.1, Math.max(0, frameMs / 1000));
    previous = now;
    driveParameters(renderer, frame + config.warmupFrames);
    const p0 = performance.now();
    physics.update(dt, renderer.parameters);
    const p1 = performance.now();
    drawCalls = renderer.render();
    const p2 = performance.now();
    frameSamples.push(frameMs);
    physicsSamples.push(p1 - p0);
    submitSamples.push(p2 - p1);
  }

  renderer.setGpuTimingEnabled(false);
  const gpuSamples = await renderer.collectGpuTimings();
  const gpuTiming = {
    ...renderer.gpuTiming,
    samples: gpuSamples.length,
    coverage: config.sampleFrames > 0 ? gpuSamples.length / config.sampleFrames : 0
  };
  renderer.destroy();

  const notes = [
    "Frame latency uses requestAnimationFrame and is display-refresh limited.",
    "submitCpuMs measures CPU submission only; it is not GPU completion time.",
    "gpuMs measures all backend-native visual render work, including mask passes when present.",
    "GPU timing is optional and never falls back to synchronous gl.finish()/per-frame queue waits."
  ];
  if (visual) {
    notes.push("R8A visual case includes texture sampling, premultiplied blending, soft masks and configured overdraw.");
    notes.push("maskTargetBytes estimates full-frame RGBA8 targets; it intentionally exposes the cost of the v1 simple mask architecture.");
  } else {
    notes.push("Core R7 case has no declared textures or clipping masks.");
  }
  if (!gpuTiming.supported) notes.push(`GPU timing unavailable: ${gpuTiming.reason ?? "unknown reason"}`);

  return {
    schemaVersion: 1,
    case: config,
    backend,
    environment: {
      userAgent: navigator.userAgent,
      devicePixelRatio: dpr,
      width: canvas.width,
      height: canvas.height,
      estimatedRefreshHz: estimateRefreshHz(calibration),
      timestamp: new Date().toISOString()
    },
    samples: config.sampleFrames,
    frameMs: summarize(frameSamples),
    submitCpuMs: summarize(submitSamples),
    physicsMs: summarize(physicsSamples),
    gpuMs: gpuSamples.length > 0 ? summarize(gpuSamples) : undefined,
    gpuTiming,
    drawCalls,
    staticGpuBytesEstimate: estimateStaticBytes(pkg) + (visual?.textureGpuBytesEstimate ?? 0) + (visual?.maskTargetBytes ?? 0),
    parameterBytesPerFullUpload: config.parameters * 4,
    visual,
    fallbackReason: selection.fallbackReason,
    notes
  };
}
