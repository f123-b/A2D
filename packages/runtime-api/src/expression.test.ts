import test from "node:test";
import assert from "node:assert/strict";
import { ParameterCore } from "./parameterCore.js";
import { applyExpressionPreset } from "./expression.js";

test("expression set and add bindings blend deterministically", () => {
  const core = new ParameterCore([
    { id: "mouth", min: -1, max: 1, default: 0 },
    { id: "brow", min: -1, max: 1, default: 0 }
  ]);

  applyExpressionPreset(core, {
    id: "happy",
    bindings: [
      { parameterId: "mouth", mode: "set", value: 0.8 },
      { parameterId: "brow", mode: "add", value: 0.4 }
    ]
  }, 0.5);

  assert.ok(Math.abs(core.get("mouth") - 0.4) < 1e-6);
  assert.ok(Math.abs(core.get("brow") - 0.2) < 1e-6);
});

test("expression output is clamped by ParameterCore", () => {
  const core = new ParameterCore([{ id: "p", min: -1, max: 1, default: 0 }]);
  applyExpressionPreset(core, {
    id: "large",
    bindings: [{ parameterId: "p", mode: "add", value: 4 }]
  });
  assert.equal(core.get("p"), 1);
});
