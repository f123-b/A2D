import test from "node:test";
import assert from "node:assert/strict";
import { ParameterCore } from "./parameterCore.js";

const defs = [
  { id: "A", min: -1, max: 1, default: 0 },
  { id: "B", min: 0, max: 10, default: 5 }
];

test("clamps and tracks dirty range", () => {
  const core = new ParameterCore(defs);
  assert.equal(core.get("A"), 0);
  assert.equal(core.set("A", 4), true);
  assert.equal(core.get("A"), 1);
  assert.deepEqual(core.consumeDirtyRange(), { start: 0, endExclusive: 1 });
  assert.equal(core.consumeDirtyRange(), null);
});

test("reset restores defaults", () => {
  const core = new ParameterCore(defs);
  core.set("B", 8);
  core.reset();
  assert.equal(core.get("B"), 5);
});
