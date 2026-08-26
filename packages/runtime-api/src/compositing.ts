export type Rgba = readonly [number, number, number, number];

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function premultiply(color: Rgba): [number, number, number, number] {
  const a = clamp01(color[3]);
  return [clamp01(color[0]) * a, clamp01(color[1]) * a, clamp01(color[2]) * a, a];
}

export function applyOpacityPremultiplied(color: Rgba, opacity: number): [number, number, number, number] {
  const k = clamp01(opacity);
  return [color[0] * k, color[1] * k, color[2] * k, color[3] * k];
}

export function overPremultiplied(src: Rgba, dst: Rgba): [number, number, number, number] {
  const inv = 1 - clamp01(src[3]);
  return [src[0] + dst[0] * inv, src[1] + dst[1] * inv, src[2] + dst[2] * inv, src[3] + dst[3] * inv];
}

export function unionMaskCoverage(sourceAlphas: readonly number[]): number {
  let uncovered = 1;
  for (const alpha of sourceAlphas) uncovered *= 1 - clamp01(alpha);
  return 1 - uncovered;
}

export function clipCoverage(sourceAlphas: readonly number[], mode: "inside" | "outside"): number {
  const coverage = unionMaskCoverage(sourceAlphas);
  return mode === "inside" ? coverage : 1 - coverage;
}

export function premultiplyRgba8(bytes: Uint8Array): Uint8Array {
  if (bytes.byteLength % 4 !== 0) throw new Error("RGBA8 byte length must be divisible by 4");
  const out = bytes.slice();
  for (let i = 0; i < out.length; i += 4) {
    const a = out[i + 3] / 255;
    out[i] = Math.round(out[i] * a);
    out[i + 1] = Math.round(out[i + 1] * a);
    out[i + 2] = Math.round(out[i + 2] * a);
  }
  return out;
}
