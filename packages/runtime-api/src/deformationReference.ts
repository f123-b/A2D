import type { Parameter, Pseudo3DHeadData } from "@a2d/avatar-schema";

export interface MorphInfluence {
  parameterIndex: number;
  deltaX: number;
  deltaY: number;
  weight: number;
}

export function normalizeParameter(def: Parameter, value: number): number {
  const clamped = Math.min(def.max, Math.max(def.min, value));
  if (clamped === def.default) return 0;

  if (clamped > def.default) {
    const denom = def.max - def.default;
    return denom === 0 ? 0 : Math.min(1, (clamped - def.default) / denom);
  }

  const denom = def.default - def.min;
  return denom === 0 ? 0 : Math.max(-1, (clamped - def.default) / denom);
}

export function applyMorphs(
  x: number,
  y: number,
  definitions: readonly Parameter[],
  values: Float32Array,
  influences: readonly MorphInfluence[]
): [number, number] {
  let outX = x;
  let outY = y;

  for (const influence of influences) {
    const def = definitions[influence.parameterIndex];
    if (!def) continue;
    const n = normalizeParameter(def, values[influence.parameterIndex] ?? def.default);
    outX += n * influence.weight * influence.deltaX;
    outY += n * influence.weight * influence.deltaY;
  }

  return [outX, outY];
}

export function applyPseudo3DHead(
  x: number,
  y: number,
  proxyZ: number,
  angleXDeg: number,
  angleYDeg: number,
  data: Pseudo3DHeadData
): [number, number] {
  const x0 = x - data.pivot[0];
  const y0 = y - data.pivot[1];
  const z0 = proxyZ * data.depthScale;

  const yaw = angleXDeg * data.yawGain * Math.PI / 180;
  const pitch = angleYDeg * data.pitchGain * Math.PI / 180;

  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);

  const x1 = cy * x0 + sy * z0;
  const z1 = -sy * x0 + cy * z0;

  const y1 = cp * y0 - sp * z1;
  const z2 = sp * y0 + cp * z1;

  // Perspective is relative to the vertex's neutral proxy depth so that
  // ParamAngleX/Y = 0 preserves the authored 2D pose exactly.
  const depthDelta = z2 - z0;
  const perspectiveScale = 1 / Math.max(0.25, 1 + data.perspective * depthDelta);

  return [
    x1 * perspectiveScale + data.pivot[0],
    y1 * perspectiveScale + data.pivot[1]
  ];
}

export function applyRoll(
  x: number,
  y: number,
  angleZDeg: number,
  pivot: readonly [number, number]
): [number, number] {
  const a = angleZDeg * Math.PI / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const x0 = x - pivot[0];
  const y0 = y - pivot[1];
  return [
    c * x0 - s * y0 + pivot[0],
    s * x0 + c * y0 + pivot[1]
  ];
}
