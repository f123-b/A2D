import type { LoadedA2DPackage } from "@a2d/runtime-api";
import { compileVisualRenderPlan } from "@a2d/runtime-api";
import type { BenchmarkCase } from "./contract.js";
import { createSyntheticAvatar } from "./syntheticAvatar.js";

export interface VisualCostEstimate {
  textureCount: number;
  textureAssetBytes: number;
  textureGpuBytesEstimate: number;
  maskPasses: number;
  maskSourceDraws: number;
  mainDraws: number;
  maskTargetBytes: number;
}

function makeTexture(size: number): Uint8Array {
  if (!Number.isInteger(size) || size < 1 || size > 4096) throw new Error("invalid visual texture size");
  const pixels = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const checker = ((x >> 4) ^ (y >> 4)) & 1;
      const alpha = 176 + ((x + y) % 80);
      pixels[i] = checker ? 210 : 90;
      pixels[i + 1] = 90 + ((x * 7 + y * 3) % 120);
      pixels[i + 2] = checker ? 120 : 220;
      pixels[i + 3] = alpha;
    }
  }
  return pixels;
}

export function createVisualSyntheticAvatar(config: BenchmarkCase): LoadedA2DPackage {
  if (!config.visual) return createSyntheticAvatar(config);
  const pkg = createSyntheticAvatar(config);
  const profile = config.visual;
  if (!(profile.overdrawScale > 0 && profile.overdrawScale <= 1)) throw new Error("overdrawScale must be within (0,1]");
  if (!Number.isInteger(profile.maskGroups) || profile.maskGroups < 0 || profile.maskGroups > Math.floor(config.parts / 2)) {
    throw new Error("maskGroups must be 0..floor(parts/2)");
  }

  const original = pkg.buffers.get("synthetic");
  if (!original) throw new Error("synthetic buffer missing");
  const binary = original.slice(0);
  const parts = pkg.model.parts.map(part => ({
    ...part,
    material: { textureId: "bench-atlas", opacity: 1, blendMode: "normal" as const },
    mesh: { ...part.mesh }
  }));

  if (profile.overdrawScale < 1) {
    for (const part of parts) {
      const view = part.mesh.positions;
      const positions = new Float32Array(binary, view.byteOffset, view.byteLength / 4);
      for (let i = 0; i < positions.length; i++) {
        positions[i] = 0.5 + (positions[i] - 0.5) * profile.overdrawScale;
      }
    }
  }

  for (let group = 0; group < profile.maskGroups; group++) {
    const source = parts[group];
    const target = parts[parts.length - 1 - group];
    target.clip = {
      sources: [source.id],
      mode: group & 1 ? "outside" : "inside"
    };
  }

  const texture = makeTexture(profile.textureSize);
  const textureUri = "textures/bench-atlas.rgba";
  const model = {
    ...pkg.model,
    textures: [{
      id: "bench-atlas",
      uri: textureUri,
      byteLength: texture.byteLength,
      format: "rgba8" as const,
      width: profile.textureSize,
      height: profile.textureSize,
      alphaMode: "straight" as const,
      filter: "linear" as const
    }],
    parts
  };

  return {
    ...pkg,
    model,
    buffers: new Map([["synthetic", binary]]),
    assets: new Map([[textureUri, texture.buffer]])
  };
}

export function createBenchmarkAvatar(config: BenchmarkCase): LoadedA2DPackage {
  return config.visual ? createVisualSyntheticAvatar(config) : createSyntheticAvatar(config);
}

export function estimateVisualCost(pkg: LoadedA2DPackage, width: number, height: number): VisualCostEstimate | undefined {
  if (!(pkg.model.textures?.length || pkg.model.parts.some(part => part.clip))) return undefined;
  const plan = compileVisualRenderPlan(pkg.model);
  const clipByKey = new Map<string, readonly number[]>();
  for (const item of plan.items) {
    if (item.clip && !clipByKey.has(item.clip.key)) clipByKey.set(item.clip.key, item.clip.sourcePartIndices);
  }
  let textureAssetBytes = 0;
  let textureGpuBytesEstimate = 0;
  for (const texture of pkg.model.textures ?? []) {
    textureAssetBytes += texture.byteLength;
    textureGpuBytesEstimate += texture.width && texture.height
      ? texture.width * texture.height * 4
      : texture.byteLength;
  }
  let maskSourceDraws = 0;
  for (const sources of clipByKey.values()) maskSourceDraws += sources.length;
  return {
    textureCount: pkg.model.textures?.length ?? 0,
    textureAssetBytes,
    textureGpuBytesEstimate,
    maskPasses: clipByKey.size,
    maskSourceDraws,
    mainDraws: plan.items.length,
    maskTargetBytes: clipByKey.size * width * height * 4
  };
}
