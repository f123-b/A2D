import test from "node:test";
import assert from "node:assert/strict";
import type { AvatarModelV1 } from "@a2d/avatar-schema";
import { compileVisualRenderPlan } from "./visualPlan.js";

const emptyView = { buffer: "g", byteOffset: 0, byteLength: 0, componentType: "f32" as const, count: 0 };
const mesh = { positions: emptyView, uvs: emptyView, indices: { ...emptyView, componentType: "u16" as const } };
const base: AvatarModelV1 = {
  formatVersion: 1, id: "visual", canvas: { width: 1, height: 1 },
  buffers: [{ id: "g", uri: "buffers/g.bin", byteLength: 0 }],
  textures: [{ id: "atlas", uri: "textures/atlas.rgba", byteLength: 4, format: "rgba8", width: 1, height: 1 }],
  parameters: [], deformers: [],
  parts: [
    { id: "eye-white", semantic: "eye_l", drawOrder: 0, material: { textureId: "atlas" }, mesh },
    { id: "iris", semantic: "iris_l", drawOrder: 1, material: { textureId: "atlas", opacity: 0.8 }, clip: { sources: ["eye-white"], mode: "inside" }, mesh }
  ]
};

test("visual plan resolves texture and clip source indices", () => {
  const plan = compileVisualRenderPlan(base);
  assert.equal(plan.items[1].textureId, "atlas");
  assert.equal(plan.items[1].clip?.key, "inside:eye-white");
  assert.deepEqual(plan.items[1].clip?.sourcePartIndices, [0]);
});

test("visual plan rejects unknown texture", () => {
  const model = structuredClone(base);
  model.parts[0].material = { textureId: "missing" };
  assert.throws(() => compileVisualRenderPlan(model), /unknown texture/);
});

test("visual plan rejects self clipping", () => {
  const model = structuredClone(base);
  model.parts[0].clip = { sources: ["eye-white"], mode: "inside" };
  assert.throws(() => compileVisualRenderPlan(model), /cannot reference itself/);
});
