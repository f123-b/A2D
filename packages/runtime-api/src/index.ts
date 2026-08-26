import type { AvatarModelV1 } from "@a2d/avatar-schema";

export * from "./packageLoader.js";
export * from "./parameterCore.js";
export * from "./webgl2Renderer.js";

export type RenderBackend = "webgpu" | "webgl2";
export interface RuntimeStats { frameMs: number; cpuMs: number; physicsMs: number; gpuMs?: number; drawCalls: number; visibleParts: number; vertices: number; }
export interface AvatarInstance {
  readonly model: AvatarModelV1;
  readonly parameterValues: Float32Array;
  setParameter(index: number, value: number): void;
  setParameters(values: Float32Array): void;
  update(dtSeconds: number): void;
  render(): void;
  getStats(): RuntimeStats;
  destroy(): void;
}
export interface A2DRuntime { readonly backend: RenderBackend; load(packageBytes: ArrayBuffer): Promise<AvatarInstance>; }

export * from "./deformationReference.js";
export * from "./deformationBuffers.js";
export * from "./webgl2DeformationRenderer.js";
export * from "./physics.js";
export * from "./physicsFactory.js";
export * from "./webgpuDeformationRenderer.js";
export * from "./runtimeBackend.js";
export * from "./webgpuLayout.js";
export * from "./gpuTiming.js";
export * from "./compositing.js";
export * from "./textureResources.js";
export * from "./visualTextures.js";
export * from "./visualPlan.js";
export * from "./webgl2VisualRenderer.js";
export * from "./webgpuVisualRenderer.js";
