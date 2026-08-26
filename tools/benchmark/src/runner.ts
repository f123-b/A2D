import {
  createBestDeformationRenderer,
  createPhysicsFromModel,
  type DeformationRenderer
} from "@a2d/runtime-api";
import type { BenchmarkCase } from "./contract.js";
import { createSyntheticAvatar, estimateStaticBytes } from "./syntheticAvatar.js";
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
  drawCalls: number;
  staticGpuBytesEstimate: number;
  parameterBytesPerFullUpload: number;
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
  const pkg = createSyntheticAvatar(config);
  const dpr = devicePixelRatio || 1;
  canvas.style.width = `${1920 / dpr}px`;
  canvas.style.height = `${1080 / dpr}px`;
  canvas.width = 1920;
  canvas.height = 1080;

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
  for (let frame = 0; frame < config.warmupFrames; frame++) {
    const now = await nextFrame();
    const dt = Math.min(0.1, Math.max(0, (now - previous) / 1000));
    previous = now;
    driveParameters(renderer, frame);
    physics.update(dt, renderer.parameters);
    renderer.render();
  }

  const frameSamples: number[] = [];
  const submitSamples: number[] = [];
  const physicsSamples: number[] = [];
  let drawCalls = 0;

  onProgress?.(`sampling ${config.id} on ${backend}`);
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

  renderer.destroy();

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
    drawCalls,
    staticGpuBytesEstimate: estimateStaticBytes(pkg),
    parameterBytesPerFullUpload: config.parameters * 4,
    fallbackReason: selection.fallbackReason,
    notes: [
      "Frame latency uses requestAnimationFrame and is display-refresh limited.",
      "submitCpuMs measures CPU submission only; it is not GPU completion time.",
      "R7 v1 excludes texture atlas, clipping masks and overdraw-heavy art."
    ]
  };
}
