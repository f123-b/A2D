import test from "node:test";
import assert from "node:assert/strict";
import type { AvatarModelV1 } from "@a2d/avatar-schema";
import {
  packWebGPUHeadUniforms,
  packWebGPUMorphInfluences,
  packWebGPUParameterDefinitions,
  WEBGPU_HEAD_UNIFORM_BYTES
} from "./webgpuLayout.js";

const model: AvatarModelV1 = {
  formatVersion: 1,
  id: "webgpu-layout-test",
  canvas: { width: 1, height: 1 },
  buffers: [{ id: "d", uri: "d.bin", byteLength: 16 }],
  parameters: [
    { id: "ParamAngleX", min: -30, max: 30, default: 0 },
    { id: "ParamAngleY", min: -20, max: 20, default: 0 },
    { id: "ParamAngleZ", min: -15, max: 15, default: 0 }
  ],
  parts: [],
  deformers: [{
    id: "head",
    type: "pseudo3d_head",
    targets: [],
    data: {
      pivot: [0.4, 0.6],
      radius: [0.5, 0.6],
      depthScale: 0.25,
      perspective: 0.35,
      yawGain: 1.1,
      pitchGain: 0.9
    }
  }],
  deformationBuffers: {
    morphInfluences: {
      view: { buffer: "d", byteOffset: 0, byteLength: 16, count: 1, stride: 16 },
      strideBytes: 16
    }
  }
};

function assertClose(actual: number, expected: number, epsilon = 1e-6): void {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} != ${expected}`);
}

test("parameter definitions are packed as vec4 records", () => {
  const packed = packWebGPUParameterDefinitions(model.parameters);
  assert.equal(packed.length, 12);
  assert.deepEqual(Array.from(packed.slice(0, 4)), [-30, 30, 0, 0]);
});

test("mixed Avatar IR morph record is repacked to GPU vec4", () => {
  const raw = new ArrayBuffer(16);
  const view = new DataView(raw);
  view.setUint32(0, 7, true);
  view.setFloat32(4, 0.25, true);
  view.setFloat32(8, -0.5, true);
  view.setFloat32(12, 0.75, true);

  const packed = packWebGPUMorphInfluences({
    manifest: { containerVersion: 1, model: "model.json", entryBuffers: ["d.bin"] },
    model,
    buffers: new Map([["d", raw]])
  });

  assert.deepEqual(Array.from(packed), [7, 0.25, -0.5, 0.75]);
});

test("head uniform layout is exactly 48 bytes and keeps integer indices", () => {
  const indices = new Map<string, number>([
    ["ParamAngleX", 0], ["ParamAngleY", 1], ["ParamAngleZ", 2]
  ]);
  const packed = packWebGPUHeadUniforms(model, indices);
  assert.equal(packed.byteLength, WEBGPU_HEAD_UNIFORM_BYTES);

  const f32 = new Float32Array(packed);
  const i32 = new Int32Array(packed);
  [0.4, 0.6, 0.25, 0.35, 1.1, 0.9].forEach((expected, i) => {
    assertClose(f32[i], expected);
  });
  assert.deepEqual(Array.from(i32.slice(8, 12)), [0, 1, 2, -1]);
});
