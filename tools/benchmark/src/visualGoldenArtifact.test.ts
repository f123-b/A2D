import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import crypto from "node:crypto";

const root = new URL("../../../spec/examples/", import.meta.url);

function readJson(name: string): any {
  return JSON.parse(fs.readFileSync(new URL(name, root), "utf8"));
}

test("R8A visual golden source model has the expected visual/physics capabilities", () => {
  const model = readJson("r8a-visual-golden-model.json");
  const metadata = readJson("r8a-visual-golden-metadata.json");
  assert.equal(model.parts.length, metadata.expected.parts);
  assert.equal(model.textures.length, metadata.expected.textures);
  assert.equal(model.parts.filter((part: any) => part.clip).length, metadata.expected.clipGroups);
  assert.equal(model.physics.length, metadata.expected.physicsChains);
  assert.equal(model.deformationBuffers.morphInfluences.view.count, metadata.expected.morphInfluences);
  assert.deepEqual(model.parts.find((part: any) => part.id === "iris-l").clip, {
    sources: ["eye-white-l"],
    mode: "inside"
  });
  assert.deepEqual(model.parts.find((part: any) => part.id === "iris-r").clip, {
    sources: ["eye-white-r"],
    mode: "inside"
  });
});

test("R8A visual golden packaged artifact is byte-stable", () => {
  const metadata = readJson("r8a-visual-golden-metadata.json");
  const bytes = fs.readFileSync(new URL("r8a-visual-golden.a2d", root));
  const sha = crypto.createHash("sha256").update(bytes).digest("hex");
  assert.equal(sha, metadata.sha256);
});
