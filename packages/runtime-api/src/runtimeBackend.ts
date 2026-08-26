import type { AvatarModelV1 } from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "./packageLoader.js";
import { ParameterCore } from "./parameterCore.js";
import { WebGL2DeformationRenderer } from "./webgl2DeformationRenderer.js";
import { WebGPUDeformationRenderer } from "./webgpuDeformationRenderer.js";

export interface DeformationRenderer {
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
}

export async function createBestDeformationRenderer(
  canvas: HTMLCanvasElement,
  pkg: LoadedA2DPackage,
  options?: { preferWebGPU?: boolean; requireWebGPU?: boolean }
): Promise<RendererSelection> {
  const preferWebGPU = options?.preferWebGPU ?? true;

  if (preferWebGPU && WebGPUDeformationRenderer.isSupported()) {
    try {
      return { renderer: await WebGPUDeformationRenderer.create(canvas, pkg) };
    } catch (error) {
      if (options?.requireWebGPU) throw error;
      return {
        renderer: new WebGL2DeformationRenderer(canvas, pkg),
        fallbackReason: error instanceof Error ? error.message : String(error)
      };
    }
  }

  if (options?.requireWebGPU) {
    throw new Error("WebGPU is required but unavailable");
  }

  return {
    renderer: new WebGL2DeformationRenderer(canvas, pkg),
    fallbackReason: preferWebGPU ? "WebGPU is unavailable" : undefined
  };
}
