import {
  createBestDeformationRenderer,
  createPhysicsFromModel,
  type DeformationRenderer,
  loadA2DFromZip
} from "@a2d/runtime-api";
import { zipReaderFromArrayBuffer } from "@a2d/runtime-api/jsZipReader";

const fileInput = document.querySelector<HTMLInputElement>("#file")!;
const canvas = document.querySelector<HTMLCanvasElement>("#stage")!;
const angle = document.querySelector<HTMLInputElement>("#angle")!;
const angleValue = document.querySelector<HTMLSpanElement>("#angleValue")!;
const mouth = document.querySelector<HTMLInputElement>("#mouth")!;
const mouthValue = document.querySelector<HTMLSpanElement>("#mouthValue")!;
const status = document.querySelector<HTMLDivElement>("#status")!;
const reset = document.querySelector<HTMLButtonElement>("#reset")!;

let renderer: DeformationRenderer | null = null;
let physics: ReturnType<typeof createPhysicsFromModel> | null = null;
let fallbackReason: string | undefined;
let raf = 0;
let last = performance.now();
let frameTimes: number[] = [];
let cpuTimes: number[] = [];

function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p));
  return sorted[index];
}

function requestedBackend(): { preferWebGPU: boolean; requireWebGPU: boolean } {
  const backend = new URLSearchParams(location.search).get("backend");
  if (backend === "webgl2") return { preferWebGPU: false, requireWebGPU: false };
  if (backend === "webgpu") return { preferWebGPU: true, requireWebGPU: true };
  return { preferWebGPU: true, requireWebGPU: false };
}

function loop(now: number) {
  raf = requestAnimationFrame(loop);
  if (!renderer || !physics) {
    last = now;
    return;
  }

  const dt = Math.min(0.1, Math.max(0, (now - last) / 1000));
  last = now;

  const t0 = performance.now();
  const physicsStats = physics.update(dt, renderer.parameters);
  const drawCalls = renderer.render();
  const cpuMs = performance.now() - t0;

  frameTimes.push(dt * 1000);
  cpuTimes.push(cpuMs);

  if (frameTimes.length >= 120) {
    const hair = renderer.parameters.indexById.has("ParamHairX")
      ? renderer.parameters.get("ParamHairX")
      : 0;

    status.textContent =
      `backend: ${renderer.backend}\n` +
      `${fallbackReason ? `fallback: ${fallbackReason}\n` : ""}` +
      `parts: ${renderer.model.parts.length}\n` +
      `parameters: ${renderer.model.parameters.length}\n` +
      `physics chains: ${physics.chains.length}\n` +
      `physics substeps: ${physicsStats.subSteps}\n` +
      `ParamHairX: ${hair.toFixed(4)}\n` +
      `draw calls: ${drawCalls}\n` +
      `frame p50: ${percentile(frameTimes, 0.50).toFixed(2)} ms\n` +
      `frame p95: ${percentile(frameTimes, 0.95).toFixed(2)} ms\n` +
      `frame p99: ${percentile(frameTimes, 0.99).toFixed(2)} ms\n` +
      `submit cpu p95: ${percentile(cpuTimes, 0.95).toFixed(3)} ms`;

    frameTimes = [];
    cpuTimes = [];
  }
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;

  try {
    status.textContent = "loading...";
    renderer?.destroy();
    renderer = null;
    physics = null;
    fallbackReason = undefined;

    const bytes = await file.arrayBuffer();
    const reader = await zipReaderFromArrayBuffer(bytes);
    const pkg = await loadA2DFromZip(reader);

    const selection = await createBestDeformationRenderer(canvas, pkg, requestedBackend());
    renderer = selection.renderer;
    fallbackReason = selection.fallbackReason;
    physics = createPhysicsFromModel(pkg.model, {
      physicsHz: 120,
      maxFrameDt: 0.1,
      maxSubSteps: 12
    });

    angle.value = renderer.parameters.indexById.has("ParamAngleX")
      ? String(renderer.parameters.get("ParamAngleX"))
      : "0";
    angleValue.textContent = angle.value;

    mouth.value = renderer.parameters.indexById.has("ParamMouthOpenY")
      ? String(renderer.parameters.get("ParamMouthOpenY"))
      : "0";
    mouthValue.textContent = mouth.value;

    status.textContent =
      `loaded: ${pkg.model.name ?? pkg.model.id}\n` +
      `backend: ${renderer.backend}\n` +
      `${fallbackReason ? `fallback: ${fallbackReason}\n` : ""}` +
      `parts: ${pkg.model.parts.length}\n` +
      `physics chains: ${physics.chains.length}`;
  } catch (error) {
    console.error(error);
    status.textContent = error instanceof Error ? error.message : String(error);
  }
});

angle.addEventListener("input", () => {
  angleValue.textContent = angle.value;
  if (renderer?.parameters.indexById.has("ParamAngleX")) {
    renderer.setParameter("ParamAngleX", Number(angle.value));
  }
});

mouth.addEventListener("input", () => {
  mouthValue.textContent = mouth.value;
  if (renderer?.parameters.indexById.has("ParamMouthOpenY")) {
    renderer.setParameter("ParamMouthOpenY", Number(mouth.value));
  }
});

reset.addEventListener("click", () => {
  renderer?.parameters.reset();
  physics?.reset();

  if (renderer?.parameters.indexById.has("ParamAngleX")) {
    angle.value = String(renderer.parameters.get("ParamAngleX"));
    angleValue.textContent = angle.value;
  }
  if (renderer?.parameters.indexById.has("ParamMouthOpenY")) {
    mouth.value = String(renderer.parameters.get("ParamMouthOpenY"));
    mouthValue.textContent = mouth.value;
  }
});

raf = requestAnimationFrame(loop);
window.addEventListener("beforeunload", () => {
  cancelAnimationFrame(raf);
  renderer?.destroy();
});
