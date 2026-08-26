import test from "node:test";
import assert from "node:assert/strict";
import { STANDARD_PARAMETER_IDS } from "@a2d/avatar-schema";
import { buildR8BFullGoldenA2D, createR8BFullGoldenPackage, R8B_FULL_GOLDEN_COUNTS } from "./fullGoldenFixture.js";
import { loadA2DFromZip } from "./packageLoader.js";
import { zipReaderFromArrayBuffer } from "./jsZipReader.js";

test("R8B full golden factory covers the Phase-1 avatar contract", async () => {
  const source = createR8BFullGoldenPackage();
  assert.equal(source.model.parts.length, R8B_FULL_GOLDEN_COUNTS.parts);
  assert.equal(source.model.parameters.length, R8B_FULL_GOLDEN_COUNTS.parameters);
  assert.equal(source.model.physics?.length, R8B_FULL_GOLDEN_COUNTS.physics);
  assert.equal(source.model.expressions?.length, R8B_FULL_GOLDEN_COUNTS.expressions);

  const bytes = await buildR8BFullGoldenA2D();
  const loaded = await loadA2DFromZip(await zipReaderFromArrayBuffer(bytes));
  const model = loaded.model;
  const parameterIds = new Set(model.parameters.map(value => value.id));
  for (const id of STANDARD_PARAMETER_IDS) assert.ok(parameterIds.has(id), `missing ${id}`);

  for (const id of ["ParamHairFrontX", "ParamHairSideLX", "ParamHairSideRX", "ParamHairBackX"])
    assert.ok(parameterIds.has(id), `missing ${id}`);

  assert.deepEqual(model.expressions?.map(value => value.id), ["happy", "surprised", "angry"]);
  assert.deepEqual(model.parts.find(p => p.id === "iris-l")?.clip, { sources: ["eye-white-l"], mode: "inside" });
  assert.deepEqual(model.parts.find(p => p.id === "iris-r")?.clip, { sources: ["eye-white-r"], mode: "inside" });
  assert.equal(model.parts.find(p => p.id === "face")?.parent, "body");
  assert.equal(model.parts.find(p => p.id === "iris-l")?.parent, "eye-white-l");

  const ref = model.deformationBuffers?.morphInfluences?.view;
  assert.ok(ref && ref.count > 0);
  const geometry = loaded.buffers.get(ref!.buffer)!;
  const data = new DataView(geometry, ref!.byteOffset, ref!.byteLength);
  const morphParameterIndices = new Set<number>();
  for (let i = 0; i < ref!.count; i++) morphParameterIndices.add(data.getUint32(i * 16, true));

  for (const id of [
    "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ", "ParamBreath",
    "ParamEyeLOpen", "ParamEyeROpen", "ParamEyeBallX", "ParamEyeBallY",
    "ParamMouthOpenY", "ParamMouthForm", "ParamBrowLY", "ParamBrowRY",
    "ParamBrowLAngle", "ParamBrowRAngle", "ParamHairFrontX", "ParamHairSideLX",
    "ParamHairSideRX", "ParamHairBackX"
  ]) {
    const index = model.parameters.findIndex(p => p.id === id);
    assert.ok(morphParameterIndices.has(index), `no morph influence for ${id}`);
  }
});
