import type { AvatarModelV1 } from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "./packageLoader.js";
import { ParameterCore } from "./parameterCore.js";
import type { GpuTimingController } from "./gpuTiming.js";
import { WebGL2DeformationRenderer } from "./webgl2DeformationRenderer.js";
import { WebGPUDeformationRenderer } from "./webgpuDeformationRenderer.js";
import { WebGL2VisualRenderer } from "./webgl2VisualRenderer.js";
import { WebGPUVisualRenderer } from "./webgpuVisualRenderer.js";
import { hasVisualResources } from "./visualRuntimeMode.js";

export interface DeformationRenderer extends GpuTimingController {
  readonly backend: "webgpu" | "webgl2";
  readonly model: AvatarModelV1;
  readonly parameters: ParameterCore;
  setParameter(id: string, value: number): void;
  render(): number;
  destroy(): void;
}

export interface RendererSelection {
  renderer: DeformationRenderer;
  fallbackReason?: string;
  visual: boolean;
}

export async function createBestDeformationRenderer(
  canvas: HTMLCanvasElement,
  pkg: LoadedA2DPackage,
  options?: { preferWebGPU?: boolean; requireWebGPU?: boolean }
): Promise<RendererSelection> {
  const preferWebGPU = options?.preferWebGPU ?? true;
  const visual = hasVisualResources(pkg.model);

  if (preferWebGPU && WebGPUDeformationRenderer.isSupported()) {
    try {
      const renderer = visual
        ? await WebGPUVisualRenderer.create(canvas, pkg)
        : await WebGPUDeformationRenderer.create(canvas, pkg);
      return { renderer, visual };
    } catch (error) {
      if (options?.requireWebGPU) throw error;
      const renderer = visual
        ? await WebGL2VisualRenderer.create(canvas, pkg)
        : new WebGL2DeformationRenderer(canvas, pkg);
      return {
        renderer,
        visual,
        fallbackReason: error instanceof Error ? error.message : String(error)
      };
    }
  }

  if (options?.requireWebGPU) throw new Error("WebGPU is required but unavailable");
  const renderer = visual
    ? await WebGL2VisualRenderer.create(canvas, pkg)
    : new WebGL2DeformationRenderer(canvas, pkg);
  return {
    renderer,
    visual,
    fallbackReason: preferWebGPU ? "WebGPU is unavailable" : undefined
  };
}
