import test from "node:test";
import assert from "node:assert/strict";
import { clipCoverage, overPremultiplied, premultiply, premultiplyRgba8, unionMaskCoverage } from "./compositing.js";

test("premultiplied over matches source-over", () => {
  const src = premultiply([1, 0, 0, 0.5]);
  const dst = premultiply([0, 0, 1, 1]);
  assert.deepEqual(overPremultiplied(src, dst), [0.5, 0, 0.5, 1]);
});

test("multi-source mask uses alpha union", () => {
  assert.ok(Math.abs(unionMaskCoverage([0.5, 0.5]) - 0.75) < 1e-12);
  assert.ok(Math.abs(clipCoverage([0.5, 0.5], "outside") - 0.25) < 1e-12);
});

test("RGBA8 straight alpha is premultiplied once", () => {
  assert.deepEqual([...premultiplyRgba8(new Uint8Array([200, 100, 50, 128]))], [100, 50, 25, 128]);
});
