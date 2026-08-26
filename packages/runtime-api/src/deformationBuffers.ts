export const MORPH_INFLUENCE_STRIDE_BYTES = 16;

export interface PackedMorphInfluence {
  parameterIndex: number;
  deltaX: number;
  deltaY: number;
  weight: number;
}

export function packMorphInfluences(
  influences: readonly PackedMorphInfluence[]
): ArrayBuffer {
  const buffer = new ArrayBuffer(influences.length * MORPH_INFLUENCE_STRIDE_BYTES);
  const view = new DataView(buffer);

  influences.forEach((inf, i) => {
    const base = i * MORPH_INFLUENCE_STRIDE_BYTES;
    view.setUint32(base + 0, inf.parameterIndex, true);
    view.setFloat32(base + 4, inf.deltaX, true);
    view.setFloat32(base + 8, inf.deltaY, true);
    view.setFloat32(base + 12, inf.weight, true);
  });

  return buffer;
}

export function unpackMorphInfluence(
  buffer: ArrayBuffer,
  index: number
): PackedMorphInfluence {
  const base = index * MORPH_INFLUENCE_STRIDE_BYTES;
  if (base < 0 || base + MORPH_INFLUENCE_STRIDE_BYTES > buffer.byteLength) {
    throw new RangeError(`morph influence index out of range: ${index}`);
  }

  const view = new DataView(buffer);
  return {
    parameterIndex: view.getUint32(base + 0, true),
    deltaX: view.getFloat32(base + 4, true),
    deltaY: view.getFloat32(base + 8, true),
    weight: view.getFloat32(base + 12, true)
  };
}
