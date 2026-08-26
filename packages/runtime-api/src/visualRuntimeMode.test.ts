import test from "node:test";
import assert from "node:assert/strict";
import type { AvatarModelV1 } from "@a2d/avatar-schema";
import { buildVisualMaskPasses, hasVisualResources } from "./visualRuntimeMode.js";
import type { VisualRenderPlan } from "./visualPlan.js";

function model(): AvatarModelV1 {
  return {
    formatVersion: 1,
    id: "visual",
    canvas: { width: 1, height: 1 },
    buffers: [], parameters: [], deformers: [], physics: [],
    textures: [{ id: "atlas", uri: "textures/a.rgba", byteLength: 4, format: "rgba8", width: 1, height: 1 }],
    parts: []
  };
}

test("visual resources select visual backends", () => {
  assert.equal(hasVisualResources(model()), true);
  const plain = model(); plain.textures = [];
  assert.equal(hasVisualResources(plain), false);
});

test("clip consumers sharing a key compile to one mask pass", () => {
  const plan: VisualRenderPlan = {
    textureIds: new Set(["atlas"]),
    clipKeys: new Set(["inside:eye"]),
    items: [
      { partId: "eye", partIndex: 0, drawOrder: 0, opacity: 1, blendMode: "normal" },
      { partId: "iris", partIndex: 1, drawOrder: 1, opacity: 1, blendMode: "normal", clip: { key: "inside:eye", mode: "inside", sourcePartIds: ["eye"], sourcePartIndices: [0] } },
      { partId: "shine", partIndex: 2, drawOrder: 2, opacity: 1, blendMode: "normal", clip: { key: "inside:eye", mode: "inside", sourcePartIds: ["eye"], sourcePartIndices: [0] } }
    ]
  };
  const passes = buildVisualMaskPasses(plan);
  assert.equal(passes.length, 1);
  assert.equal(passes[0].key, "inside:eye");
  assert.deepEqual(passes[0].sourcePartIds, ["eye"]);
});
