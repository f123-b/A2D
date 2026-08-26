import type {
  AvatarModelV1,
  BufferView,
  Parameter,
  Part,
  SpringChainPhysics
} from "@a2d/avatar-schema";
import type { LoadedA2DPackage } from "@a2d/runtime-api";
import type { BenchmarkCase } from "./contract.js";

interface Segment {
  byteOffset: number;
  byteLength: number;
}

class BinaryBuilder {
  private readonly chunks: Uint8Array[] = [];
  private length = 0;

  private align4(): void {
    const pad = (4 - (this.length & 3)) & 3;
    if (pad) {
      this.chunks.push(new Uint8Array(pad));
      this.length += pad;
    }
  }

  append(view: ArrayBufferView): Segment {
    this.align4();
    const byteOffset = this.length;
    const bytes = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
    const copy = new Uint8Array(bytes);
    this.chunks.push(copy);
    this.length += copy.byteLength;
    return { byteOffset, byteLength: copy.byteLength };
  }

  finish(): ArrayBuffer {
    this.align4();
    const out = new Uint8Array(this.length);
    let offset = 0;
    for (const chunk of this.chunks) {
      out.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return out.buffer;
  }
}

function bufferView(
  segment: Segment,
  componentType: BufferView["componentType"],
  count: number,
  stride?: number
): BufferView {
  const view: BufferView = {
    buffer: "synthetic",
    byteOffset: segment.byteOffset,
    byteLength: segment.byteLength,
    componentType,
    count
  };
  if (stride !== undefined) view.stride = stride;
  return view;
}

function createParameters(count: number): Parameter[] {
  if (count < 8 || count > 256) throw new Error("synthetic parameter count must be 8..256");
  const standard: Parameter[] = [
    { id: "ParamAngleX", min: -30, max: 30, default: 0 },
    { id: "ParamAngleY", min: -30, max: 30, default: 0 },
    { id: "ParamAngleZ", min: -30, max: 30, default: 0 },
    { id: "ParamMouthOpenY", min: 0, max: 1, default: 0 },
    { id: "ParamEyeLOpen", min: 0, max: 1, default: 1 },
    { id: "ParamEyeROpen", min: 0, max: 1, default: 1 },
    { id: "ParamBodyAngleX", min: -30, max: 30, default: 0 },
    { id: "ParamBreath", min: 0, max: 1, default: 0 }
  ];
  while (standard.length < count) {
    standard.push({
      id: `ParamSynthetic${standard.length}`,
      min: -1,
      max: 1,
      default: 0
    });
  }
  return standard;
}

function createPhysics(count: number, parameters: readonly Parameter[]): SpringChainPhysics[] {
  const outputs = parameters.slice(8);
  if (count > 0 && outputs.length === 0) throw new Error("physics requires synthetic output parameters");
  return Array.from({ length: count }, (_, index) => {
    const output = outputs[index % outputs.length];
    return {
      id: `bench-physics-${index}`,
      type: "spring_chain",
      nodeCount: 5,
      segmentLength: 0.035 + (index % 4) * 0.005,
      root: [0.5, 0.15],
      gravity: [0, 0.7],
      damping: 0.08,
      stiffness: 0.94,
      maxDisplacement: 1,
      inputBindings: [
        { parameterId: "ParamAngleX", axis: "x", gain: 0.002 + (index % 3) * 0.0005 }
      ],
      outputBindings: [
        {
          parameterId: output.id,
          axis: "x",
          source: "tip",
          gain: 1.5,
          min: output.min,
          max: output.max
        }
      ]
    };
  });
}

export function createSyntheticAvatar(config: BenchmarkCase): LoadedA2DPackage {
  if (config.vertices % 4 !== 0) throw new Error("vertices must be divisible by 4");
  if (config.parts < 1 || config.parts > config.vertices / 4) throw new Error("invalid part count");
  if (config.influencesPerVertex < 0 || config.influencesPerVertex > 8) {
    throw new Error("influencesPerVertex must be 0..8");
  }

  const parameters = createParameters(config.parameters);
  const totalQuads = config.vertices / 4;
  const quadsPerPart = Math.floor(totalQuads / config.parts);
  let extraQuads = totalQuads % config.parts;
  const builder = new BinaryBuilder();
  const parts: Part[] = [];
  const morphRecords: Array<[number, number, number, number]> = [];
  let globalVertex = 0;

  const gridColumns = Math.ceil(Math.sqrt(totalQuads));
  const gridRows = Math.ceil(totalQuads / gridColumns);
  const cellW = 0.92 / gridColumns;
  const cellH = 0.92 / gridRows;
  let quadCursor = 0;

  for (let partIndex = 0; partIndex < config.parts; partIndex++) {
    const quadCount = quadsPerPart + (extraQuads-- > 0 ? 1 : 0);
    const vertexCount = quadCount * 4;
    const positions = new Float32Array(vertexCount * 2);
    const uvs = new Float32Array(vertexCount * 2);
    const proxyZ = new Float32Array(vertexCount);
    const ranges = new Uint32Array(vertexCount * 2);
    const indices = new Uint16Array(quadCount * 6);

    for (let q = 0; q < quadCount; q++) {
      const globalQuad = quadCursor++;
      const col = globalQuad % gridColumns;
      const row = Math.floor(globalQuad / gridColumns);
      const left = 0.04 + col * cellW;
      const top = 0.04 + row * cellH;
      const right = left + cellW * 0.82;
      const bottom = top + cellH * 0.82;
      const v = q * 4;

      positions.set([left, top, right, top, right, bottom, left, bottom], v * 2);
      uvs.set([0, 0, 1, 0, 1, 1, 0, 1], v * 2);
      indices.set([v, v + 1, v + 2, v, v + 2, v + 3], q * 6);

      for (let local = 0; local < 4; local++) {
        const vertex = v + local;
        const z = 0.2 + 0.15 * Math.sin((globalVertex + vertex) * 0.017);
        proxyZ[vertex] = z;
        ranges[vertex * 2] = morphRecords.length;
        ranges[vertex * 2 + 1] = config.influencesPerVertex;

        for (let influence = 0; influence < config.influencesPerVertex; influence++) {
          const parameterIndex = 8 + ((globalVertex + vertex + influence * 17) % Math.max(1, parameters.length - 8));
          const phase = (globalVertex + vertex) * 0.013 + influence * 0.7;
          morphRecords.push([
            Math.min(parameterIndex, parameters.length - 1),
            Math.sin(phase) * 0.0015,
            Math.cos(phase) * 0.0015,
            0.25 + influence * 0.1
          ]);
        }
      }
    }
    globalVertex += vertexCount;

    const posSeg = builder.append(positions);
    const uvSeg = builder.append(uvs);
    const zSeg = builder.append(proxyZ);
    const rangeSeg = builder.append(ranges);
    const indexSeg = builder.append(indices);

    parts.push({
      id: `part-${partIndex}`,
      semantic: partIndex === 0 ? "face" : "other",
      drawOrder: partIndex,
      textureAtlas: null,
      mesh: {
        positions: bufferView(posSeg, "f32", vertexCount, 8),
        uvs: bufferView(uvSeg, "f32", vertexCount, 8),
        indices: bufferView(indexSeg, "u16", indices.length),
        proxyZ: bufferView(zSeg, "f32", vertexCount, 4),
        influenceRanges: bufferView(rangeSeg, "u32", vertexCount, 8)
      }
    });
  }

  const morphBuffer = new ArrayBuffer(morphRecords.length * 16);
  const morphView = new DataView(morphBuffer);
  morphRecords.forEach((record, index) => {
    const offset = index * 16;
    morphView.setUint32(offset, record[0], true);
    morphView.setFloat32(offset + 4, record[1], true);
    morphView.setFloat32(offset + 8, record[2], true);
    morphView.setFloat32(offset + 12, record[3], true);
  });
  const morphSeg = builder.append(new Uint8Array(morphBuffer));
  const binary = builder.finish();

  const model: AvatarModelV1 = {
    formatVersion: 1,
    id: `bench-${config.id}`,
    name: `Benchmark ${config.id}`,
    canvas: { width: 1, height: 1 },
    buffers: [{ id: "synthetic", uri: "memory://synthetic", byteLength: binary.byteLength }],
    parameters,
    parts,
    deformers: [{
      id: "bench-head",
      type: "pseudo3d_head",
      targets: parts.map(part => part.id),
      parameterBindings: [
        { parameterId: "ParamAngleX" },
        { parameterId: "ParamAngleY" },
        { parameterId: "ParamAngleZ" }
      ],
      data: {
        pivot: [0.5, 0.5],
        radius: [0.5, 0.6],
        depthScale: 0.25,
        perspective: 0.25,
        yawGain: 1,
        pitchGain: 1
      }
    }],
    deformationBuffers: {
      morphInfluences: {
        view: {
          buffer: "synthetic",
          byteOffset: morphSeg.byteOffset,
          byteLength: morphSeg.byteLength,
          count: morphRecords.length,
          stride: 16
        },
        strideBytes: 16
      }
    },
    physics: createPhysics(config.physicsChains, parameters)
  };

  return {
    manifest: { containerVersion: 1, model: "memory://model", entryBuffers: ["memory://synthetic"] },
    model,
    buffers: new Map([["synthetic", binary]])
  };
}

export function estimateStaticBytes(pkg: LoadedA2DPackage): number {
  let total = 0;
  for (const part of pkg.model.parts) {
    total += part.mesh.positions.byteLength;
    total += part.mesh.uvs.byteLength;
    total += part.mesh.indices.byteLength;
    total += part.mesh.proxyZ?.byteLength ?? 0;
    total += part.mesh.influenceRanges?.byteLength ?? 0;
  }
  total += pkg.model.deformationBuffers?.morphInfluences?.view.byteLength ?? 0;
  total += Math.max(16, pkg.model.parameters.length * 16);
  total += Math.max(4, pkg.model.parameters.length * 4);
  total += 48;
  return total;
}
