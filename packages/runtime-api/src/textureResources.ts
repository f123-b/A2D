import type { TextureResourceV1 } from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "./packageLoader.js";
import { premultiplyRgba8 } from "./compositing.js";

export type DecodedTexture =
  | { kind: "rgba8"; width: number; height: number; pixels: Uint8Array; filter: "linear" | "nearest" }
  | { kind: "image-bitmap"; width: number; height: number; bitmap: ImageBitmap; filter: "linear" | "nearest" };

function bytesFor(pkg: LoadedA2DPackage, texture: TextureResourceV1): ArrayBuffer {
  const bytes = pkg.assets?.get(texture.uri);
  if (!bytes) throw new Error(`texture asset not loaded: ${texture.uri}`);
  return bytes;
}

export async function decodeTextureResource(pkg: LoadedA2DPackage, texture: TextureResourceV1): Promise<DecodedTexture> {
  const buffer = bytesFor(pkg, texture);
  const filter = texture.filter ?? "linear";
  if (texture.format === "rgba8") {
    if (!texture.width || !texture.height) throw new Error(`texture ${texture.id}: rgba8 requires width/height`);
    const expected = texture.width * texture.height * 4;
    if (buffer.byteLength !== expected) throw new Error(`texture ${texture.id}: rgba8 length mismatch`);
    let pixels = new Uint8Array(buffer.slice(0));
    if ((texture.alphaMode ?? "straight") === "straight") pixels = premultiplyRgba8(pixels);
    return { kind: "rgba8", width: texture.width, height: texture.height, pixels, filter };
  }

  const mime = texture.format === "png" ? "image/png" : "image/webp";
  const bitmap = await createImageBitmap(new Blob([buffer], { type: mime }), {
    premultiplyAlpha: "premultiply",
    colorSpaceConversion: "default"
  });
  return { kind: "image-bitmap", width: bitmap.width, height: bitmap.height, bitmap, filter };
}
