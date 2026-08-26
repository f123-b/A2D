import type { AvatarModelV1, Part } from "@a2d/avatar-schema";
import { createTypedView, type LoadedA2DPackage } from "./packageLoader.js";
import { ParameterCore } from "./parameterCore.js";
import type { GpuTimingInfo } from "./gpuTiming.js";
import {
  packWebGPUHeadUniforms,
  packWebGPUMorphInfluences,
  packWebGPUParameterDefinitions
} from "./webgpuLayout.js";

type GpuBufferUsage = number;
type GpuTextureUsage = number;
type GpuMapMode = number;
type GpuFeatureSet = { has(name: string): boolean };
type GpuBuffer = {
  destroy(): void;
  mapAsync(mode: number): Promise<void>;
  getMappedRange(): ArrayBuffer;
  unmap(): void;
};
type GpuShaderModule = object;
type GpuBindGroup = object;
type GpuBindGroupLayout = object;
type GpuPipelineLayout = object;
type GpuRenderPipeline = object;
type GpuTextureView = object;
type GpuQuerySet = { destroy(): void };
type GpuRenderPass = {
  setPipeline(pipeline: GpuRenderPipeline): void;
  setBindGroup(index: number, bindGroup: GpuBindGroup): void;
  setVertexBuffer(slot: number, buffer: GpuBuffer): void;
  setIndexBuffer(buffer: GpuBuffer, format: "uint16" | "uint32"): void;
  drawIndexed(indexCount: number): void;
  end(): void;
};
type GpuCommandEncoder = {
  beginRenderPass(descriptor: unknown): GpuRenderPass;
  resolveQuerySet(querySet: GpuQuerySet, firstQuery: number, queryCount: number, destination: GpuBuffer, destinationOffset: number): void;
  copyBufferToBuffer(source: GpuBuffer, sourceOffset: number, destination: GpuBuffer, destinationOffset: number, size: number): void;
  finish(): object;
};
type GpuQueue = {
  writeBuffer(buffer: GpuBuffer, bufferOffset: number, data: ArrayBuffer | ArrayBufferView, dataOffset?: number, size?: number): void;
  submit(commands: object[]): void;
};
type GpuDevice = {
  queue: GpuQueue;
  lost: Promise<{ message?: string }>;
  createBuffer(descriptor: unknown): GpuBuffer;
  createShaderModule(descriptor: unknown): GpuShaderModule;
  createBindGroupLayout(descriptor: unknown): GpuBindGroupLayout;
  createPipelineLayout(descriptor: unknown): GpuPipelineLayout;
  createRenderPipeline(descriptor: unknown): GpuRenderPipeline;
  createBindGroup(descriptor: unknown): GpuBindGroup;
  createCommandEncoder(descriptor?: unknown): GpuCommandEncoder;
  createQuerySet(descriptor: unknown): GpuQuerySet;
  destroy(): void;
};
type GpuAdapter = {
  features: GpuFeatureSet;
  requestDevice(descriptor?: { requiredFeatures?: string[] }): Promise<GpuDevice>;
};
type GpuApi = {
  requestAdapter(options?: unknown): Promise<GpuAdapter | null>;
  getPreferredCanvasFormat(): string;
};
type GpuCanvasContext = {
  configure(descriptor: unknown): void;
  getCurrentTexture(): { createView(): GpuTextureView };
};
type GpuTimingSlot = {
  querySet: GpuQuerySet;
  resolveBuffer: GpuBuffer;
  readBuffer: GpuBuffer;
  pending: boolean;
  promise: Promise<void> | null;
};

const GPU_BUFFER_USAGE = {
  MAP_READ: 0x0001,
  COPY_SRC: 0x0004,
  COPY_DST: 0x0008,
  INDEX: 0x0010,
  VERTEX: 0x0020,
  UNIFORM: 0x0040,
  STORAGE: 0x0080,
  QUERY_RESOLVE: 0x0200
} as const satisfies Record<string, GpuBufferUsage>;
const GPU_TEXTURE_USAGE = { RENDER_ATTACHMENT: 0x0010 } as const satisfies Record<string, GpuTextureUsage>;
const GPU_MAP_MODE = { READ: 0x0001 } as const satisfies Record<string, GpuMapMode>;
const MAX_VERTEX_INFLUENCES = 8;
const TIMING_RING_SIZE = 8;
const TIMESTAMP_BYTES = 16;

const WGSL = /* wgsl */ `
struct HeadUniforms {
  head0: vec4<f32>,
  head1: vec4<f32>,
  parameterIndices: vec4<i32>,
};
@group(0) @binding(0) var<storage, read> parameters: array<f32>;
@group(0) @binding(1) var<storage, read> parameterDefs: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> morphInfluences: array<vec4<f32>>;
@group(0) @binding(3) var<uniform> head: HeadUniforms;
struct VertexInput {
  @location(0) position: vec2<f32>,
  @location(1) uv: vec2<f32>,
  @location(2) proxyZ: f32,
  @location(3) influenceOffset: u32,
  @location(4) influenceCount: u32,
};
struct VertexOutput {
  @builtin(position) position: vec4<f32>,
  @location(0) uv: vec2<f32>,
};
fn normalizedParameter(index: u32) -> f32 {
  let value = parameters[index];
  let def = parameterDefs[index];
  let minV = def.x;
  let maxV = def.y;
  let defaultV = def.z;
  if (value >= defaultV) {
    let denom = maxV - defaultV;
    if (denom == 0.0) { return 0.0; }
    return clamp((value - defaultV) / denom, 0.0, 1.0);
  }
  let denom = defaultV - minV;
  if (denom == 0.0) { return 0.0; }
  return clamp((value - defaultV) / denom, -1.0, 0.0);
}
fn parameterOrZero(index: i32) -> f32 {
  if (index < 0) { return 0.0; }
  return parameters[u32(index)];
}
@vertex
fn vsMain(input: VertexInput) -> VertexOutput {
  var p = input.position;
  let count = min(input.influenceCount, ${MAX_VERTEX_INFLUENCES}u);
  for (var i = 0u; i < ${MAX_VERTEX_INFLUENCES}u; i = i + 1u) {
    if (i >= count) { break; }
    let rec = morphInfluences[input.influenceOffset + i];
    let parameterIndex = u32(round(rec.x));
    let n = normalizedParameter(parameterIndex);
    p = p + n * rec.w * rec.yz;
  }
  let angleX = parameterOrZero(head.parameterIndices.x);
  let angleY = parameterOrZero(head.parameterIndices.y);
  let angleZ = parameterOrZero(head.parameterIndices.z);
  let pivot = head.head0.xy;
  let depthScale = head.head0.z;
  let perspective = head.head0.w;
  let yawGain = head.head1.x;
  let pitchGain = head.head1.y;
  let local = p - pivot;
  let z0 = input.proxyZ * depthScale;
  let yaw = radians(angleX * yawGain);
  let pitch = radians(angleY * pitchGain);
  let cy = cos(yaw);
  let sy = sin(yaw);
  let cp = cos(pitch);
  let sp = sin(pitch);
  let x1 = cy * local.x + sy * z0;
  let z1 = -sy * local.x + cy * z0;
  let y1 = cp * local.y - sp * z1;
  let z2 = sp * local.y + cp * z1;
  let depthDelta = z2 - z0;
  let perspectiveScale = 1.0 / max(0.25, 1.0 + perspective * depthDelta);
  p = vec2<f32>(x1, y1) * perspectiveScale + pivot;
  let roll = radians(angleZ);
  let cr = cos(roll);
  let sr = sin(roll);
  let rollLocal = p - pivot;
  p = vec2<f32>(cr * rollLocal.x - sr * rollLocal.y, sr * rollLocal.x + cr * rollLocal.y) + pivot;
  var out: VertexOutput;
  out.position = vec4<f32>(p.x * 2.0 - 1.0, 1.0 - p.y * 2.0, 0.0, 1.0);
  out.uv = input.uv;
  return out;
}
@fragment
fn fsMain(input: VertexOutput) -> @location(0) vec4<f32> {
  return vec4<f32>(input.uv.x, 1.0 - input.uv.y, 0.9, 1.0);
}`;

type PartGpu = {
  part: Part;
  positionBuffer: GpuBuffer;
  uvBuffer: GpuBuffer;
  proxyZBuffer: GpuBuffer;
  influenceRangeBuffer: GpuBuffer;
  indexBuffer: GpuBuffer;
  indexCount: number;
  indexFormat: "uint16" | "uint32";
};

function navigatorGpu(): GpuApi | null {
  return (navigator as Navigator & { gpu?: GpuApi }).gpu ?? null;
}
function createBufferWithData(device: GpuDevice, data: ArrayBufferView, usage: number, label: string): GpuBuffer {
  const byteLength = Math.max(4, (data.byteLength + 3) & ~3);
  const buffer = device.createBuffer({ label, size: byteLength, usage: usage | GPU_BUFFER_USAGE.COPY_DST });
  if (data.byteLength > 0) device.queue.writeBuffer(buffer, 0, data);
  return buffer;
}
function createTimingSlots(device: GpuDevice): GpuTimingSlot[] {
  return Array.from({ length: TIMING_RING_SIZE }, (_, index) => ({
    querySet: device.createQuerySet({ label: `a2d.timing.query.${index}`, type: "timestamp", count: 2 }),
    resolveBuffer: device.createBuffer({
      label: `a2d.timing.resolve.${index}`,
      size: TIMESTAMP_BYTES,
      usage: GPU_BUFFER_USAGE.QUERY_RESOLVE | GPU_BUFFER_USAGE.COPY_SRC
    }),
    readBuffer: device.createBuffer({
      label: `a2d.timing.read.${index}`,
      size: TIMESTAMP_BYTES,
      usage: GPU_BUFFER_USAGE.COPY_DST | GPU_BUFFER_USAGE.MAP_READ
    }),
    pending: false,
    promise: null
  }));
}

export class WebGPUDeformationRenderer {
  readonly backend = "webgpu" as const;
  readonly model: AvatarModelV1;
  readonly parameters: ParameterCore;
  readonly gpuTiming: GpuTimingInfo;
  private readonly canvas: HTMLCanvasElement;
  private readonly context: GpuCanvasContext;
  private readonly device: GpuDevice;
  private readonly format: string;
  private readonly pipeline: GpuRenderPipeline;
  private readonly bindGroup: GpuBindGroup;
  private readonly parameterBuffer: GpuBuffer;
  private readonly parameterDefBuffer: GpuBuffer;
  private readonly influenceBuffer: GpuBuffer;
  private readonly headUniformBuffer: GpuBuffer;
  private readonly parts: PartGpu[] = [];
  private readonly timingSlots: GpuTimingSlot[];
  private readonly gpuTimingSamples: number[] = [];
  private gpuTimingEnabled = false;
  private lost = false;

  static isSupported(): boolean { return navigatorGpu() !== null; }
  static async create(canvas: HTMLCanvasElement, pkg: LoadedA2DPackage): Promise<WebGPUDeformationRenderer> {
    const gpu = navigatorGpu();
    if (!gpu) throw new Error("WebGPU is unavailable");
    const adapter = await gpu.requestAdapter({ powerPreference: "high-performance" });
    if (!adapter) throw new Error("WebGPU adapter is unavailable");
    const timestampSupported = adapter.features.has("timestamp-query");
    const device = await adapter.requestDevice(timestampSupported ? { requiredFeatures: ["timestamp-query"] } : undefined);
    const context = canvas.getContext("webgpu") as unknown as GpuCanvasContext | null;
    if (!context) { device.destroy(); throw new Error("WebGPU canvas context is unavailable"); }
    return new WebGPUDeformationRenderer(canvas, pkg, device, context, gpu.getPreferredCanvasFormat(), timestampSupported);
  }

  private constructor(canvas: HTMLCanvasElement, pkg: LoadedA2DPackage, device: GpuDevice, context: GpuCanvasContext, format: string, timestampSupported: boolean) {
    this.canvas = canvas;
    this.context = context;
    this.device = device;
    this.format = format;
    this.model = pkg.model;
    this.parameters = new ParameterCore(pkg.model.parameters);
    this.gpuTiming = timestampSupported
      ? { supported: true, source: "webgpu-timestamp-query" }
      : { supported: false, reason: "WebGPU adapter does not expose timestamp-query" };
    this.timingSlots = timestampSupported ? createTimingSlots(device) : [];
    this.context.configure({ device: this.device, format: this.format, alphaMode: "premultiplied", usage: GPU_TEXTURE_USAGE.RENDER_ATTACHMENT });
    const parameterData = this.parameters.values.length > 0 ? this.parameters.values : new Float32Array(1);
    this.parameterBuffer = createBufferWithData(device, parameterData, GPU_BUFFER_USAGE.STORAGE, "a2d.parameters");
    this.parameterDefBuffer = createBufferWithData(device, packWebGPUParameterDefinitions(pkg.model.parameters), GPU_BUFFER_USAGE.STORAGE, "a2d.parameter-defs");
    this.influenceBuffer = createBufferWithData(device, packWebGPUMorphInfluences(pkg), GPU_BUFFER_USAGE.STORAGE, "a2d.morph-influences");
    this.headUniformBuffer = createBufferWithData(device, new Uint8Array(packWebGPUHeadUniforms(pkg.model, this.parameters.indexById)), GPU_BUFFER_USAGE.UNIFORM, "a2d.head-uniforms");
    const shader = device.createShaderModule({ label: "a2d.deformation", code: WGSL });
    const bindGroupLayout = device.createBindGroupLayout({
      label: "a2d.deformation.bind-group-layout",
      entries: [
        { binding: 0, visibility: 1, buffer: { type: "read-only-storage" } },
        { binding: 1, visibility: 1, buffer: { type: "read-only-storage" } },
        { binding: 2, visibility: 1, buffer: { type: "read-only-storage" } },
        { binding: 3, visibility: 1, buffer: { type: "uniform" } }
      ]
    });
    const pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
    this.pipeline = device.createRenderPipeline({
      label: "a2d.deformation.pipeline",
      layout: pipelineLayout,
      vertex: {
        module: shader,
        entryPoint: "vsMain",
        buffers: [
          { arrayStride: 8, attributes: [{ shaderLocation: 0, offset: 0, format: "float32x2" }] },
          { arrayStride: 8, attributes: [{ shaderLocation: 1, offset: 0, format: "float32x2" }] },
          { arrayStride: 4, attributes: [{ shaderLocation: 2, offset: 0, format: "float32" }] },
          { arrayStride: 8, attributes: [{ shaderLocation: 3, offset: 0, format: "uint32" }, { shaderLocation: 4, offset: 4, format: "uint32" }] }
        ]
      },
      fragment: { module: shader, entryPoint: "fsMain", targets: [{ format: this.format }] },
      primitive: { topology: "triangle-list", cullMode: "none" }
    });
    this.bindGroup = device.createBindGroup({
      label: "a2d.deformation.bind-group",
      layout: bindGroupLayout,
      entries: [
        { binding: 0, resource: { buffer: this.parameterBuffer } },
        { binding: 1, resource: { buffer: this.parameterDefBuffer } },
        { binding: 2, resource: { buffer: this.influenceBuffer } },
        { binding: 3, resource: { buffer: this.headUniformBuffer } }
      ]
    });
    const sorted = [...pkg.model.parts].sort((a, b) => a.drawOrder - b.drawOrder);
    for (const part of sorted) this.parts.push(this.createPart(pkg, part));
    void device.lost.then(info => {
      this.lost = true;
      console.error(`A2D WebGPU device lost${info.message ? `: ${info.message}` : ""}`);
    });
  }

  private createPart(pkg: LoadedA2DPackage, part: Part): PartGpu {
    const positions = createTypedView(pkg.buffers, part.mesh.positions);
    const uvs = createTypedView(pkg.buffers, part.mesh.uvs);
    const indices = createTypedView(pkg.buffers, part.mesh.indices);
    if (!(positions instanceof Float32Array) || !(uvs instanceof Float32Array)) throw new Error(`${part.id}: positions/uvs must be f32`);
    if (!(indices instanceof Uint16Array || indices instanceof Uint32Array)) throw new Error(`${part.id}: indices must be u16/u32`);
    const vertexCount = positions.length / 2;
    let proxyZ = new Float32Array(vertexCount);
    if (part.mesh.proxyZ) {
      const value = createTypedView(pkg.buffers, part.mesh.proxyZ);
      if (!(value instanceof Float32Array) || value.length !== vertexCount) throw new Error(`${part.id}: invalid proxyZ`);
      proxyZ = value;
    }
    let ranges = new Uint32Array(vertexCount * 2);
    if (part.mesh.influenceRanges) {
      const value = createTypedView(pkg.buffers, part.mesh.influenceRanges);
      if (!(value instanceof Uint32Array) || value.length !== vertexCount * 2) throw new Error(`${part.id}: invalid influenceRanges`);
      ranges = value;
    }
    return {
      part,
      positionBuffer: createBufferWithData(this.device, positions, GPU_BUFFER_USAGE.VERTEX, `${part.id}.positions`),
      uvBuffer: createBufferWithData(this.device, uvs, GPU_BUFFER_USAGE.VERTEX, `${part.id}.uvs`),
      proxyZBuffer: createBufferWithData(this.device, proxyZ, GPU_BUFFER_USAGE.VERTEX, `${part.id}.proxyZ`),
      influenceRangeBuffer: createBufferWithData(this.device, ranges, GPU_BUFFER_USAGE.VERTEX, `${part.id}.influence-ranges`),
      indexBuffer: createBufferWithData(this.device, indices, GPU_BUFFER_USAGE.INDEX, `${part.id}.indices`),
      indexCount: indices.length,
      indexFormat: indices instanceof Uint32Array ? "uint32" : "uint16"
    };
  }

  setParameter(id: string, value: number): void { this.parameters.set(id, value); }
  setGpuTimingEnabled(enabled: boolean): void { this.gpuTimingEnabled = enabled && this.gpuTiming.supported; }
  async collectGpuTimings(): Promise<number[]> {
    const pending = this.timingSlots.map(slot => slot.promise).filter((value): value is Promise<void> => value !== null);
    if (pending.length > 0) await Promise.allSettled(pending);
    return this.gpuTimingSamples.splice(0, this.gpuTimingSamples.length);
  }
  private flushDirtyParameters(): void {
    const range = this.parameters.consumeDirtyRange();
    if (!range) return;
    this.device.queue.writeBuffer(this.parameterBuffer, range.start * 4, this.parameters.values.subarray(range.start, range.endExclusive));
  }
  private acquireTimingSlot(): GpuTimingSlot | null {
    if (!this.gpuTimingEnabled) return null;
    return this.timingSlots.find(slot => !slot.pending) ?? null;
  }
  private beginReadback(slot: GpuTimingSlot): void {
    slot.pending = true;
    slot.promise = slot.readBuffer.mapAsync(GPU_MAP_MODE.READ).then(() => {
      const mapped = slot.readBuffer.getMappedRange();
      const values = new BigUint64Array(mapped.slice(0, TIMESTAMP_BYTES));
      const elapsedNs = values[1] >= values[0] ? values[1] - values[0] : 0n;
      const elapsedMs = Number(elapsedNs) / 1_000_000;
      if (Number.isFinite(elapsedMs) && elapsedMs >= 0) this.gpuTimingSamples.push(elapsedMs);
      slot.readBuffer.unmap();
    }).catch(() => {}).finally(() => {
      slot.pending = false;
      slot.promise = null;
    });
  }

  render(): number {
    if (this.lost) return 0;
    const dpr = globalThis.devicePixelRatio || 1;
    const width = Math.max(1, Math.floor(this.canvas.clientWidth * dpr));
    const height = Math.max(1, Math.floor(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) { this.canvas.width = width; this.canvas.height = height; }
    this.flushDirtyParameters();
    const timingSlot = this.acquireTimingSlot();
    const encoder = this.device.createCommandEncoder({ label: "a2d.frame" });
    const descriptor: Record<string, unknown> = {
      colorAttachments: [{
        view: this.context.getCurrentTexture().createView(),
        clearValue: { r: 0.06, g: 0.06, b: 0.07, a: 0 },
        loadOp: "clear",
        storeOp: "store"
      }]
    };
    if (timingSlot) {
      descriptor.timestampWrites = { querySet: timingSlot.querySet, beginningOfPassWriteIndex: 0, endOfPassWriteIndex: 1 };
    }
    const pass = encoder.beginRenderPass(descriptor);
    pass.setPipeline(this.pipeline);
    pass.setBindGroup(0, this.bindGroup);
    let drawCalls = 0;
    for (const part of this.parts) {
      pass.setVertexBuffer(0, part.positionBuffer);
      pass.setVertexBuffer(1, part.uvBuffer);
      pass.setVertexBuffer(2, part.proxyZBuffer);
      pass.setVertexBuffer(3, part.influenceRangeBuffer);
      pass.setIndexBuffer(part.indexBuffer, part.indexFormat);
      pass.drawIndexed(part.indexCount);
      drawCalls++;
    }
    pass.end();
    if (timingSlot) {
      encoder.resolveQuerySet(timingSlot.querySet, 0, 2, timingSlot.resolveBuffer, 0);
      encoder.copyBufferToBuffer(timingSlot.resolveBuffer, 0, timingSlot.readBuffer, 0, TIMESTAMP_BYTES);
    }
    this.device.queue.submit([encoder.finish()]);
    if (timingSlot) this.beginReadback(timingSlot);
    return drawCalls;
  }

  destroy(): void {
    this.gpuTimingEnabled = false;
    for (const slot of this.timingSlots) {
      slot.querySet.destroy();
      slot.resolveBuffer.destroy();
      slot.readBuffer.destroy();
    }
    for (const part of this.parts) {
      part.positionBuffer.destroy();
      part.uvBuffer.destroy();
      part.proxyZBuffer.destroy();
      part.influenceRangeBuffer.destroy();
      part.indexBuffer.destroy();
    }
    this.parameterBuffer.destroy();
    this.parameterDefBuffer.destroy();
    this.influenceBuffer.destroy();
    this.headUniformBuffer.destroy();
    this.device.destroy();
    this.parts.length = 0;
  }
}
