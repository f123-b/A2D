import type { AvatarModelV1, Parameter, Pseudo3DHeadData } from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "./packageLoader.js";

export const WEBGPU_HEAD_UNIFORM_BYTES = 48;
export const WEBGPU_MORPH_RECORD_BYTES = 16;

export function packWebGPUParameterDefinitions(
  parameters: readonly Parameter[]
): Float32Array {
  const output = new Float32Array(Math.max(1, parameters.length) * 4);
  parameters.forEach((parameter, index) => {
    output[index * 4 + 0] = parameter.min;
    output[index * 4 + 1] = parameter.max;
    output[index * 4 + 2] = parameter.default;
    output[index * 4 + 3] = 0;
  });
  return output;
}

export function packWebGPUMorphInfluences(pkg: LoadedA2DPackage): Float32Array {
  const ref = pkg.model.deformationBuffers?.morphInfluences?.view;
  if (!ref) return new Float32Array(4);
  if (ref.byteLength % WEBGPU_MORPH_RECORD_BYTES !== 0) {
    throw new Error("morph influence byteLength must be a multiple of 16");
  }

  const source = pkg.buffers.get(ref.buffer);
  if (!source) throw new Error(`missing influence buffer ${ref.buffer}`);

  const count = ref.byteLength / WEBGPU_MORPH_RECORD_BYTES;
  const output = new Float32Array(Math.max(1, count) * 4);
  const view = new DataView(source, ref.byteOffset, ref.byteLength);

  for (let i = 0; i < count; i++) {
    const base = i * WEBGPU_MORPH_RECORD_BYTES;
    output[i * 4 + 0] = view.getUint32(base + 0, true);
    output[i * 4 + 1] = view.getFloat32(base + 4, true);
    output[i * 4 + 2] = view.getFloat32(base + 8, true);
    output[i * 4 + 3] = view.getFloat32(base + 12, true);
  }

  return output;
}

export function resolvePseudo3DHead(model: AvatarModelV1): Pseudo3DHeadData {
  const headDef = model.deformers.find(deformer => deformer.type === "pseudo3d_head");
  const data = headDef?.data as Partial<Pseudo3DHeadData> | undefined;
  return {
    pivot: data?.pivot ?? [0.5, 0.5],
    radius: data?.radius ?? [0.5, 0.6],
    depthScale: data?.depthScale ?? 0,
    perspective: data?.perspective ?? 0,
    yawGain: data?.yawGain ?? 1,
    pitchGain: data?.pitchGain ?? 1
  };
}

export function packWebGPUHeadUniforms(
  model: AvatarModelV1,
  parameterIndexById: ReadonlyMap<string, number>
): ArrayBuffer {
  const head = resolvePseudo3DHead(model);
  const output = new ArrayBuffer(WEBGPU_HEAD_UNIFORM_BYTES);
  const f32 = new Float32Array(output);
  const i32 = new Int32Array(output);

  f32.set([
    head.pivot[0], head.pivot[1], head.depthScale, head.perspective,
    head.yawGain, head.pitchGain, 0, 0
  ], 0);

  i32[8] = parameterIndexById.get("ParamAngleX") ?? -1;
  i32[9] = parameterIndexById.get("ParamAngleY") ?? -1;
  i32[10] = parameterIndexById.get("ParamAngleZ") ?? -1;
  i32[11] = -1;

  return output;
}
