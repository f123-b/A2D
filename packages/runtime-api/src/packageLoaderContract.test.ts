import test from "node:test";
import assert from "node:assert/strict";
import { loadA2DFromZip, A2DPackageError, type ZipReader } from "./packageLoader.js";

function reader(model: unknown): ZipReader {
  const files = new Map<string, string | ArrayBuffer>([
    ["manifest.json", JSON.stringify({ containerVersion: 1, model: "model.json", entryBuffers: ["buffers/g.bin"] })],
    ["model.json", JSON.stringify(model)],
    ["buffers/g.bin", new ArrayBuffer(0)]
  ]);
  return {
    has(path) { return files.has(path); },
    async readText(path) {
      const value = files.get(path);
      if (typeof value !== "string") throw new Error(path);
      return value;
    },
    async readArrayBuffer(path) {
      const value = files.get(path);
      if (!(value instanceof ArrayBuffer)) throw new Error(path);
      return value;
    }
  };
}

function part(id: string, parent?: string) {
  const zero = { buffer: "g", byteOffset: 0, byteLength: 0, componentType: "f32" as const, count: 0 };
  const indices = { ...zero, componentType: "u16" as const };
  return { id, semantic: "other" as const, parent, drawOrder: 0, mesh: { positions: zero, uvs: zero, indices } };
}

function baseModel() {
  return {
    formatVersion: 1,
    id: "validation",
    canvas: { width: 1, height: 1 },
    buffers: [{ id: "g", uri: "buffers/g.bin", byteLength: 0 }],
    parameters: [{ id: "P", min: -1, max: 1, default: 0 }],
    parts: [part("root"), part("child", "root")],
    deformers: [],
    physics: []
  };
}

test("loader rejects hierarchy cycles", async () => {
  const model = baseModel();
  model.parts = [part("a", "b"), part("b", "a")];
  await assert.rejects(() => loadA2DFromZip(reader(model)), (error: unknown) =>
    error instanceof A2DPackageError && /hierarchy contains a cycle/.test(error.message)
  );
});

test("loader rejects self-parenting", async () => {
  const model = baseModel();
  model.parts = [part("root", "root")];
  await assert.rejects(() => loadA2DFromZip(reader(model)), (error: unknown) =>
    error instanceof A2DPackageError && /cannot parent itself/.test(error.message)
  );
});

test("loader rejects expression references to missing parameters", async () => {
  const model = { ...baseModel(), expressions: [{ id: "bad", bindings: [{ parameterId: "Missing", mode: "set", value: 0 }] }] };
  await assert.rejects(() => loadA2DFromZip(reader(model)), (error: unknown) =>
    error instanceof A2DPackageError && /unknown parameter Missing/.test(error.message)
  );
});

test("loader rejects duplicate expression IDs", async () => {
  const binding = { parameterId: "P", mode: "set", value: 0.25 };
  const model = { ...baseModel(), expressions: [{ id: "same", bindings: [binding] }, { id: "same", bindings: [binding] }] };
  await assert.rejects(() => loadA2DFromZip(reader(model)), (error: unknown) =>
    error instanceof A2DPackageError && /duplicate expression id/.test(error.message)
  );
});

test("loader rejects invalid expression binding modes", async () => {
  const model = { ...baseModel(), expressions: [{ id: "bad-mode", bindings: [{ parameterId: "P", mode: "multiply", value: 0.5 }] }] };
  await assert.rejects(() => loadA2DFromZip(reader(model)), (error: unknown) =>
    error instanceof A2DPackageError && /invalid mode/.test(error.message)
  );
});

test("loader accepts valid hierarchy and expressions", async () => {
  const model = { ...baseModel(), expressions: [{ id: "ok", bindings: [{ parameterId: "P", mode: "set", value: 0.5 }] }] };
  const loaded = await loadA2DFromZip(reader(model));
  assert.equal(loaded.model.parts[1].parent, "root");
  assert.equal(loaded.model.expressions?.[0].id, "ok");
});
