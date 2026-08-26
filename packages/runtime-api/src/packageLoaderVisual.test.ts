import test from "node:test";
import assert from "node:assert/strict";
import type { AvatarModelV1 } from "@a2d/avatar-schema";
import { loadA2DFromZip, type ZipReader } from "./packageLoader.js";
import { decodeTextureResource } from "./textureResources.js";

function makeModel(textureUri = "textures/atlas.rgba"): AvatarModelV1 {
  const pos = { buffer: "g", byteOffset: 0, byteLength: 0, componentType: "f32" as const, count: 0 };
  const idx = { ...pos, componentType: "u16" as const };
  return {
    formatVersion: 1,
    id: "visual-loader",
    canvas: { width: 1, height: 1 },
    buffers: [{ id: "g", uri: "buffers/g.bin", byteLength: 0 }],
    textures: [{ id: "atlas", uri: textureUri, byteLength: 4, format: "rgba8", width: 1, height: 1 }],
    parameters: [],
    deformers: [],
    parts: [
      { id: "mask", semantic: "eye_l", drawOrder: 0, material: { textureId: "atlas" }, mesh: { positions: pos, uvs: pos, indices: idx } },
      { id: "iris", semantic: "iris_l", drawOrder: 1, material: { textureId: "atlas" }, clip: { sources: ["mask"], mode: "inside" }, mesh: { positions: pos, uvs: pos, indices: idx } }
    ]
  };
}

function readerFor(model: AvatarModelV1): ZipReader {
  const text = new Map<string, string>([
    ["manifest.json", JSON.stringify({ containerVersion: 1, model: "model.json", entryBuffers: ["buffers/g.bin"] })],
    ["model.json", JSON.stringify(model)]
  ]);
  const binary = new Map<string, ArrayBuffer>([
    ["buffers/g.bin", new ArrayBuffer(0)],
    ["textures/atlas.rgba", new Uint8Array([200, 100, 50, 128]).buffer]
  ]);
  return {
    has(path) { return text.has(path) || binary.has(path); },
    async readText(path) { const v = text.get(path); if (v === undefined) throw new Error(path); return v; },
    async readArrayBuffer(path) { const v = binary.get(path); if (!v) throw new Error(path); return v; }
  };
}

test("loader reads texture assets and raw decode premultiplies straight alpha", async () => {
  const model = makeModel();
  const pkg = await loadA2DFromZip(readerFor(model));
  assert.equal(pkg.assets?.get("textures/atlas.rgba")?.byteLength, 4);
  const decoded = await decodeTextureResource(pkg, model.textures![0]);
  assert.equal(decoded.kind, "rgba8");
  if (decoded.kind === "rgba8") assert.deepEqual([...decoded.pixels], [100, 50, 25, 128]);
});

test("loader rejects unsafe texture path", async () => {
  const model = makeModel("../escape.rgba");
  await assert.rejects(loadA2DFromZip(readerFor(model)), /safe package-relative path/);
});
