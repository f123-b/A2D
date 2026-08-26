import test from "node:test";
import assert from "node:assert/strict";
import { estimateRefreshHz, summarize } from "./statistics.js";

test("summarize calculates percentiles", () => {
  const values = Array.from({ length: 100 }, (_, index) => index + 1);
  const summary = summarize(values);
  assert.equal(summary.count, 100);
  assert.equal(summary.min, 1);
  assert.equal(summary.max, 100);
  assert.equal(summary.mean, 50.5);
  assert.ok(Math.abs(summary.p50 - 50.5) < 1e-9);
  assert.ok(Math.abs(summary.p95 - 95.05) < 1e-9);
});

test("refresh estimator identifies 60Hz and 120Hz", () => {
  assert.equal(estimateRefreshHz(Array(90).fill(1000 / 60)), 60);
  assert.equal(estimateRefreshHz(Array(90).fill(1000 / 120)), 120);
  assert.equal(estimateRefreshHz([16, 17]), null);
});
