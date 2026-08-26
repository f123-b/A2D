import JSZip from "jszip";
import type {
  AvatarModelV1,
  BufferView,
  Parameter,
  Part,
  SpringChainPhysics
} from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "./packageLoader.js";

interface Segment { byteOffset: number; byteLength: number; }

class BinaryBuilder {
  private chunks: Uint8Array[] = [];
  private length = 0;

  private align4(): void {
    const pad = (4 - (this.length & 3)) & 3;
    if (pad) { this.chunks.push(new Uint8Array(pad)); this.length += pad; }
  }

  append(view: ArrayBufferView): Segment {
    this.align4();
    const bytes = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
    const copy = new Uint8Array(bytes);
    const out = { byteOffset: this.length, byteLength: copy.byteLength };
    this.chunks.push(copy);
    this.length += copy.byteLength;
    return out;
  }

  finish(): ArrayBuffer {
    this.align4();
    const out = new Uint8Array(this.length);
    let offset = 0;
    for (const chunk of this.chunks) { out.set(chunk, offset); offset += chunk.byteLength; }
    return out.buffer;
  }
}

function view(segment: Segment, componentType: BufferView["componentType"], count: number, stride?: number): BufferView {
  return { buffer: "geometry", byteOffset: segment.byteOffset, byteLength: segment.byteLength, componentType, count, ...(stride ? { stride } : {}) };
}

const PARAMETERS: Parameter[] = [
  { id: "ParamAngleX", min: -30, max: 30, default: 0 },
  { id: "ParamAngleY", min: -30, max: 30, default: 0 },
  { id: "ParamAngleZ", min: -30, max: 30, default: 0 },
  { id: "ParamBodyAngleX", min: -20, max: 20, default: 0 },
  { id: "ParamBodyAngleY", min: -20, max: 20, default: 0 },
  { id: "ParamBodyAngleZ", min: -20, max: 20, default: 0 },
  { id: "ParamBreath", min: 0, max: 1, default: 0 },
  { id: "ParamEyeLOpen", min: 0, max: 1, default: 1 },
  { id: "ParamEyeROpen", min: 0, max: 1, default: 1 },
  { id: "ParamEyeBallX", min: -1, max: 1, default: 0 },
  { id: "ParamEyeBallY", min: -1, max: 1, default: 0 },
  { id: "ParamMouthOpenY", min: 0, max: 1, default: 0 },
  { id: "ParamMouthForm", min: -1, max: 1, default: 0 },
  { id: "ParamBrowLY", min: -1, max: 1, default: 0 },
  { id: "ParamBrowRY", min: -1, max: 1, default: 0 },
  { id: "ParamBrowLAngle", min: -1, max: 1, default: 0 },
  { id: "ParamBrowRAngle", min: -1, max: 1, default: 0 },
  { id: "ParamHairFrontX", min: -1, max: 1, default: 0 },
  { id: "ParamHairSideLX", min: -1, max: 1, default: 0 },
  { id: "ParamHairSideRX", min: -1, max: 1, default: 0 },
  { id: "ParamHairBackX", min: -1, max: 1, default: 0 }
];

const PARTS = [
  ["hair-back", "hair_back", "body", 0],
  ["body", "body", null, 1],
  ["cloth", "cloth", "body", 2],
  ["face", "face", "body", 3],
  ["brow-l", "other", "face", 4],
  ["brow-r", "other", "face", 4],
  ["eye-white-l", "eye_l", "face", 5],
  ["eye-white-r", "eye_r", "face", 5],
  ["iris-l", "iris_l", "eye-white-l", 6],
  ["iris-r", "iris_r", "eye-white-r", 6],
  ["mouth", "mouth", "face", 7],
  ["hair-side-l", "hair_side", "face", 8],
  ["hair-side-r", "hair_side", "face", 8],
  ["hair-front", "hair_front", "face", 9]
] as const;

type MorphSpec = { parameterId: string; dx?: number; dy?: number; weight?: number };
const MORPHS: Record<string, MorphSpec[]> = {
  body: [
    { parameterId: "ParamBodyAngleX", dx: 0.025 }, { parameterId: "ParamBodyAngleY", dy: 0.018 },
    { parameterId: "ParamBodyAngleZ", dx: 0.012, dy: 0.006 }, { parameterId: "ParamBreath", dy: -0.018 }
  ],
  cloth: [{ parameterId: "ParamBreath", dy: -0.012 }],
  "eye-white-l": [{ parameterId: "ParamEyeLOpen", dy: 0.018 }],
  "eye-white-r": [{ parameterId: "ParamEyeROpen", dy: 0.018 }],
  "iris-l": [{ parameterId: "ParamEyeBallX", dx: 0.018 }, { parameterId: "ParamEyeBallY", dy: 0.014 }],
  "iris-r": [{ parameterId: "ParamEyeBallX", dx: 0.018 }, { parameterId: "ParamEyeBallY", dy: 0.014 }],
  mouth: [{ parameterId: "ParamMouthOpenY", dy: 0.024 }, { parameterId: "ParamMouthForm", dx: 0.018 }],
  "brow-l": [{ parameterId: "ParamBrowLY", dy: -0.016 }, { parameterId: "ParamBrowLAngle", dx: 0.01, dy: -0.008 }],
  "brow-r": [{ parameterId: "ParamBrowRY", dy: -0.016 }, { parameterId: "ParamBrowRAngle", dx: -0.01, dy: -0.008 }],
  "hair-front": [{ parameterId: "ParamHairFrontX", dx: 0.025 }],
  "hair-side-l": [{ parameterId: "ParamHairSideLX", dx: 0.025 }],
  "hair-side-r": [{ parameterId: "ParamHairSideRX", dx: 0.025 }],
  "hair-back": [{ parameterId: "ParamHairBackX", dx: 0.02 }]
};

function physics(id: string, output: string, rootX: number, nodeCount: number, gain: number): SpringChainPhysics {
  return {
    id, type: "spring_chain", nodeCount, segmentLength: 0.05, root: [rootX, 0.14],
    gravity: [0, 0.58], damping: 0.1, stiffness: 0.92, maxDisplacement: 0.9,
    inputBindings: [
      { parameterId: "ParamAngleX", axis: "x", gain: 0.0025 },
      { parameterId: "ParamBodyAngleX", axis: "x", gain: 0.0012 }
    ],
    outputBindings: [{ parameterId: output, axis: "x", source: "tip", gain, min: -1, max: 1 }]
  };
}

function atlasPixels(): Uint8Array {
  const width = 16, height = 16;
  const pixels = new Uint8Array(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const i = (y * width + x) * 4;
    pixels[i] = 150 + x * 5; pixels[i + 1] = 110 + y * 7;
    pixels[i + 2] = 180 + ((x + y) % 8) * 8; pixels[i + 3] = 255;
  }
  return pixels;
}

export const R8B_FULL_GOLDEN_COUNTS = { parts: 14, parameters: 21, physics: 4, expressions: 3 } as const;

export function createR8BFullGoldenPackage(): LoadedA2DPackage {
  const builder = new BinaryBuilder();
  const parts: Part[] = [];
  const morphRecords: Array<[number, number, number, number]> = [];
  const parameterIndex = new Map(PARAMETERS.map((p, i) => [p.id, i]));

  PARTS.forEach(([id, semantic, parent, drawOrder], partIndex) => {
    const col = partIndex % 4, row = Math.floor(partIndex / 4);
    const left = 0.12 + col * 0.18, top = 0.08 + row * 0.18;
    const positions = new Float32Array([left, top, left + 0.14, top, left + 0.14, top + 0.14, left, top + 0.14]);
    const uvs = new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]);
    const proxyZ = new Float32Array([0.18, 0.22, 0.22, 0.18]);
    const ranges = new Uint32Array(8);
    const indices = new Uint16Array([0, 1, 2, 0, 2, 3]);
    const specs = MORPHS[id] ?? [];

    for (let vertex = 0; vertex < 4; vertex++) {
      ranges[vertex * 2] = morphRecords.length;
      ranges[vertex * 2 + 1] = specs.length;
      for (const spec of specs) morphRecords.push([
        parameterIndex.get(spec.parameterId)!, spec.dx ?? 0, spec.dy ?? 0, spec.weight ?? 1
      ]);
    }

    const p = builder.append(positions), u = builder.append(uvs), z = builder.append(proxyZ), r = builder.append(ranges), idx = builder.append(indices);
    parts.push({
      id, semantic, parent, drawOrder,
      material: { textureId: "atlas0", opacity: 1, blendMode: "normal" },
      ...(id === "iris-l" ? { clip: { sources: ["eye-white-l"], mode: "inside" as const } } : {}),
      ...(id === "iris-r" ? { clip: { sources: ["eye-white-r"], mode: "inside" as const } } : {}),
      mesh: {
        positions: view(p, "f32", 4, 8), uvs: view(u, "f32", 4, 8), indices: view(idx, "u16", 6),
        proxyZ: view(z, "f32", 4, 4), influenceRanges: view(r, "u32", 4, 8)
      }
    });
  });

  const morphBytes = new ArrayBuffer(morphRecords.length * 16);
  const morph = new DataView(morphBytes);
  morphRecords.forEach((record, i) => {
    const o = i * 16;
    morph.setUint32(o, record[0], true); morph.setFloat32(o + 4, record[1], true);
    morph.setFloat32(o + 8, record[2], true); morph.setFloat32(o + 12, record[3], true);
  });
  const morphSegment = builder.append(new Uint8Array(morphBytes));
  const geometry = builder.finish();
  const atlas = atlasPixels();

  const model: AvatarModelV1 = {
    formatVersion: 1, id: "r8b-full-golden", name: "R8B Full Golden Avatar", canvas: { width: 1, height: 1 },
    buffers: [{ id: "geometry", uri: "buffers/geometry.bin", byteLength: geometry.byteLength }],
    textures: [{ id: "atlas0", uri: "textures/atlas.rgba", byteLength: atlas.byteLength, format: "rgba8", width: 16, height: 16, alphaMode: "straight", filter: "linear" }],
    parameters: PARAMETERS.map(value => ({ ...value })), parts,
    deformers: [{
      id: "head", type: "pseudo3d_head",
      targets: parts.filter(p => p.id !== "body" && p.id !== "cloth").map(p => p.id),
      parameterBindings: [{ parameterId: "ParamAngleX" }, { parameterId: "ParamAngleY" }, { parameterId: "ParamAngleZ" }],
      data: { pivot: [0.5, 0.43], radius: [0.32, 0.38], depthScale: 0.22, perspective: 0.24, yawGain: 1, pitchGain: 1 }
    }],
    deformationBuffers: { morphInfluences: { view: { buffer: "geometry", byteOffset: morphSegment.byteOffset, byteLength: morphSegment.byteLength, count: morphRecords.length, stride: 16 }, strideBytes: 16 } },
    physics: [
      physics("hair-front-sway", "ParamHairFrontX", 0.5, 6, 2),
      physics("hair-side-l-sway", "ParamHairSideLX", 0.31, 7, 1.8),
      physics("hair-side-r-sway", "ParamHairSideRX", 0.69, 7, 1.8),
      physics("hair-back-sway", "ParamHairBackX", 0.5, 8, 1.3)
    ],
    expressions: [
      { id: "happy", label: "Happy", bindings: [
        { parameterId: "ParamMouthForm", mode: "set", value: 0.75 }, { parameterId: "ParamBrowLY", mode: "add", value: 0.25 },
        { parameterId: "ParamBrowRY", mode: "add", value: 0.25 }, { parameterId: "ParamEyeLOpen", mode: "set", value: 0.88 }, { parameterId: "ParamEyeROpen", mode: "set", value: 0.88 }
      ] },
      { id: "surprised", label: "Surprised", bindings: [
        { parameterId: "ParamMouthOpenY", mode: "set", value: 0.95 }, { parameterId: "ParamBrowLY", mode: "set", value: 0.75 },
        { parameterId: "ParamBrowRY", mode: "set", value: 0.75 }, { parameterId: "ParamEyeLOpen", mode: "set", value: 1 }, { parameterId: "ParamEyeROpen", mode: "set", value: 1 }
      ] },
      { id: "angry", label: "Angry", bindings: [
        { parameterId: "ParamMouthForm", mode: "set", value: -0.65 }, { parameterId: "ParamBrowLY", mode: "set", value: -0.25 },
        { parameterId: "ParamBrowRY", mode: "set", value: -0.25 }, { parameterId: "ParamBrowLAngle", mode: "set", value: -0.8 }, { parameterId: "ParamBrowRAngle", mode: "set", value: -0.8 }
      ] }
    ]
  };

  return {
    manifest: { containerVersion: 1, model: "model.json", entryBuffers: ["buffers/geometry.bin"] },
    model, buffers: new Map([["geometry", geometry]]), assets: new Map([["textures/atlas.rgba", atlas.buffer]])
  };
}

export async function buildR8BFullGoldenA2D(): Promise<ArrayBuffer> {
  const pkg = createR8BFullGoldenPackage();
  const zip = new JSZip();
  zip.file("manifest.json", JSON.stringify(pkg.manifest, null, 2));
  zip.file("model.json", JSON.stringify(pkg.model, null, 2));
  zip.file("buffers/geometry.bin", pkg.buffers.get("geometry")!);
  zip.file("textures/atlas.rgba", pkg.assets!.get("textures/atlas.rgba")!);
  return zip.generateAsync({ type: "arraybuffer", compression: "STORE" });
}
