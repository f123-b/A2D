import test from "node:test";
import assert from "node:assert/strict";
import { BENCHMARK_MATRIX } from "./contract.js";
import { createSyntheticAvatar, estimateStaticBytes } from "./syntheticAvatar.js";

test("all benchmark cases generate exact requested dimensions", () => {
  for (const config of BENCHMARK_MATRIX) {
    const pkg = createSyntheticAvatar(config);
    const vertices = pkg.model.parts.reduce((sum, part) => sum + part.mesh.positions.count, 0);
    assert.equal(vertices, config.vertices, config.id);
    assert.equal(pkg.model.parts.length, config.parts, config.id);
    assert.equal(pkg.model.parameters.length, config.parameters, config.id);
    assert.equal(pkg.model.physics?.length ?? 0, config.physicsChains, config.id);
    assert.ok(estimateStaticBytes(pkg) > 0);
  }
});

test("synthetic buffers are aligned and in bounds", () => {
  const pkg = createSyntheticAvatar(BENCHMARK_MATRIX[1]);
  const descriptor = pkg.model.buffers[0];
  for (const part of pkg.model.parts) {
    for (const view of [
      part.mesh.positions,
      part.mesh.uvs,
      part.mesh.indices,
      part.mesh.proxyZ!,
      part.mesh.influenceRanges!
    ]) {
      assert.equal(view.byteOffset % 4, 0);
      assert.ok(view.byteOffset + view.byteLength <= descriptor.byteLength);
    }
  }
  const morph = pkg.model.deformationBuffers!.morphInfluences!.view;
  assert.equal(morph.byteOffset % 4, 0);
  assert.ok(morph.byteOffset + morph.byteLength <= descriptor.byteLength);
});
