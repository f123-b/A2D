import test from "node:test";
import assert from "node:assert/strict";
import { VISUAL_BENCHMARK_MATRIX } from "./contract.js";
import { createVisualSyntheticAvatar, estimateVisualCost } from "./visualSyntheticAvatar.js";

test("visual benchmark cases produce texture assets and requested mask groups", () => {
  for (const config of VISUAL_BENCHMARK_MATRIX) {
    const pkg = createVisualSyntheticAvatar(config);
    const profile = config.visual!;
    assert.equal(pkg.model.textures?.length, 1, config.id);
    assert.ok(pkg.assets?.has("textures/bench-atlas.rgba"), config.id);
    assert.equal(pkg.model.parts.filter(part => part.clip).length, profile.maskGroups, config.id);
    assert.ok(pkg.model.parts.every(part => part.material?.textureId === "bench-atlas"), config.id);

    const cost = estimateVisualCost(pkg, 1920, 1080)!;
    assert.equal(cost.maskPasses, profile.maskGroups, config.id);
    assert.equal(cost.mainDraws, config.parts, config.id);
    assert.equal(cost.maskSourceDraws, profile.maskGroups, config.id);
    assert.equal(cost.textureGpuBytesEstimate, profile.textureSize * profile.textureSize * 4, config.id);
    assert.equal(cost.maskTargetBytes, profile.maskGroups * 1920 * 1080 * 4, config.id);
  }
});

test("heavy overdraw profile compresses all geometry around canvas center", () => {
  const config = VISUAL_BENCHMARK_MATRIX.find(item => item.id === "visual-overdraw-heavy")!;
  const pkg = createVisualSyntheticAvatar(config);
  const binary = pkg.buffers.get("synthetic")!;
  const scale = config.visual!.overdrawScale;
  const min = 0.5 - 0.5 * scale - 1e-6;
  const max = 0.5 + 0.5 * scale + 1e-6;
  for (const part of pkg.model.parts) {
    const view = part.mesh.positions;
    const positions = new Float32Array(binary, view.byteOffset, view.byteLength / 4);
    for (const value of positions) {
      assert.ok(value >= min && value <= max, `${value} outside ${min}..${max}`);
    }
  }
});
