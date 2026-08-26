import type { TextureResourceV1 } from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "./packageLoader.js";
import { decodeTextureResource, type DecodedTexture } from "./textureResources.js";

export interface DecodedVisualTextures {
  byId: ReadonlyMap<string, DecodedTexture>;
  dispose(): void;
}

export async function decodeVisualTextures(pkg: LoadedA2DPackage): Promise<DecodedVisualTextures> {
  const entries = await Promise.all(
    (pkg.model.textures ?? []).map(async texture => [texture.id, await decodeTextureResource(pkg, texture)] as const)
  );
  const byId = new Map(entries);
  return {
    byId,
    dispose(): void {
      for (const texture of byId.values()) {
        if (texture.kind === "image-bitmap") texture.bitmap.close();
      }
      byId.clear();
    }
  };
}

export function textureDefinitionById(
  textures: readonly TextureResourceV1[] | undefined,
  id: string
): TextureResourceV1 | undefined {
  return textures?.find(texture => texture.id === id);
}
