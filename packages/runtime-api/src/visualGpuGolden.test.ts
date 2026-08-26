import test from "node:test";
import assert from "node:assert/strict";
import { clipCoverage, overPremultiplied, premultiply } from "./compositing.js";

test("R8A visual golden: inside clip then source-over", () => {
  const iris = premultiply([1, 0.2, 0.1, 0.8]);
  const coverage = clipCoverage([0.5, 0.5], "inside");
  assert.equal(coverage, 0.75);
  const clipped = iris.map(value => value * coverage) as [number, number, number, number];
  const actual = overPremultiplied(clipped, premultiply([0.1, 0.1, 0.1, 1]));
  const expected = [0.64, 0.16, 0.1, 1];
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9));
});

test("R8A visual golden: outside clip inverts soft coverage", () => {
  assert.equal(clipCoverage([0.5, 0.5], "inside"), 0.75);
  assert.equal(clipCoverage([0.5, 0.5], "outside"), 0.25);
});
