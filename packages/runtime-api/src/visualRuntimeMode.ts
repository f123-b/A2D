import type { AvatarModelV1 } from "@a2d/avatar-schema";
import type { VisualRenderPlan } from "./visualPlan.js";

export interface VisualMaskPass {
  key: string;
  sourcePartIds: readonly string[];
}

export function hasVisualResources(model: AvatarModelV1): boolean {
  if ((model.textures?.length ?? 0) > 0) return true;
  return model.parts.some(part => Boolean(part.material?.textureId || part.clip));
}

export function buildVisualMaskPasses(plan: VisualRenderPlan): readonly VisualMaskPass[] {
  const byKey = new Map<string, VisualMaskPass>();
  for (const item of plan.items) {
    if (!item.clip || byKey.has(item.clip.key)) continue;
    byKey.set(item.clip.key, {
      key: item.clip.key,
      sourcePartIds: item.clip.sourcePartIds
    });
  }
  return [...byKey.values()];
}
