import test from "node:test";
import assert from "node:assert/strict";
import {
  applyMorphs,
  applyPseudo3DHead,
  normalizeParameter
} from "./deformationReference.js";
import {
  packMorphInfluences,
  unpackMorphInfluence
} from "./deformationBuffers.js";

test("parameter normalization is symmetric around default", () => {
  const def = { id: "P", min: -10, max: 30, default: 10 };
  assert.equal(normalizeParameter(def, 10), 0);
  assert.equal(normalizeParameter(def, 30), 1);
  assert.equal(normalizeParameter(def, -10), -1);
  assert.equal(normalizeParameter(def, 20), 0.5);
  assert.equal(normalizeParameter(def, 0), -0.5);
});

test("morph accumulation uses normalized parameter values", () => {
  const defs = [{ id: "P", min: -1, max: 1, default: 0 }];
  const values = new Float32Array([0.5]);
  const [x, y] = applyMorphs(1, 2, defs, values, [{
    parameterIndex: 0,
    deltaX: 4,
    deltaY: -2,
    weight: 0.5
  }]);
  assert.equal(x, 2);
  assert.equal(y, 1.5);
});

test("pseudo3d neutral is identity", () => {
  const data = {
    pivot: [0.5, 0.5] as [number, number],
    radius: [0.5, 0.6] as [number, number],
    depthScale: 0.2,
    perspective: 0.25,
    yawGain: 1,
    pitchGain: 1
  };
  const [x, y] = applyPseudo3DHead(0.7, 0.4, 0.3, 0, 0, data);
  assert.ok(Math.abs(x - 0.7) < 1e-9);
  assert.ok(Math.abs(y - 0.4) < 1e-9);
});

test("morph influence binary layout is stable", () => {
  const packed = packMorphInfluences([{
    parameterIndex: 7,
    deltaX: 0.25,
    deltaY: -0.5,
    weight: 0.75
  }]);
  assert.equal(packed.byteLength, 16);
  assert.deepEqual(unpackMorphInfluence(packed, 0), {
    parameterIndex: 7,
    deltaX: 0.25,
    deltaY: -0.5,
    weight: 0.75
  });
});
