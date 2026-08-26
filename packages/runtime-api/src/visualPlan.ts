import type { AvatarModelV1, ClipMaskV1, PartMaterialV1 } from "@a2d/avatar-schema";

export interface CompiledClipMask {
  key: string;
  mode: "inside" | "outside";
  sourcePartIds: readonly string[];
  sourcePartIndices: readonly number[];
}

export interface VisualDrawItem {
  partId: string;
  partIndex: number;
  drawOrder: number;
  textureId?: string;
  opacity: number;
  blendMode: "normal";
  clip?: CompiledClipMask;
}

export interface VisualRenderPlan {
  items: readonly VisualDrawItem[];
  textureIds: ReadonlySet<string>;
  clipKeys: ReadonlySet<string>;
}

function normalizeMaterial(material?: PartMaterialV1): Required<Pick<PartMaterialV1, "opacity" | "blendMode">> & Pick<PartMaterialV1, "textureId"> {
  return {
    textureId: material?.textureId,
    opacity: material?.opacity ?? 1,
    blendMode: material?.blendMode ?? "normal"
  };
}

function compileClip(clip: ClipMaskV1 | undefined, partId: string, partIndexById: ReadonlyMap<string, number>): CompiledClipMask | undefined {
  if (!clip) return undefined;
  const unique = [...new Set(clip.sources)].sort();
  if (unique.length === 0) throw new Error(`part ${partId}: clip.sources must not be empty`);
  if (unique.includes(partId)) throw new Error(`part ${partId}: clip cannot reference itself`);
  const sourcePartIndices = unique.map(id => {
    const index = partIndexById.get(id);
    if (index === undefined) throw new Error(`part ${partId}: clip source does not exist: ${id}`);
    return index;
  });
  return { key: `${clip.mode}:${unique.join(",")}`, mode: clip.mode, sourcePartIds: unique, sourcePartIndices };
}

export function compileVisualRenderPlan(model: AvatarModelV1): VisualRenderPlan {
  const textureIds = new Set((model.textures ?? []).map(texture => texture.id));
  const partIndexById = new Map(model.parts.map((part, index) => [part.id, index] as const));
  const clipKeys = new Set<string>();
  const items = model.parts.map((part, partIndex) => {
    const material = normalizeMaterial(part.material);
    if (!(material.opacity >= 0 && material.opacity <= 1)) throw new Error(`part ${part.id}: material.opacity must be within 0..1`);
    if (material.textureId && !textureIds.has(material.textureId)) throw new Error(`part ${part.id}: unknown texture ${material.textureId}`);
    const clip = compileClip(part.clip, part.id, partIndexById);
    if (clip) clipKeys.add(clip.key);
    return { partId: part.id, partIndex, drawOrder: part.drawOrder, textureId: material.textureId, opacity: material.opacity, blendMode: material.blendMode, clip } satisfies VisualDrawItem;
  });
  items.sort((a, b) => a.drawOrder - b.drawOrder || a.partIndex - b.partIndex);
  return { items, textureIds, clipKeys };
}
