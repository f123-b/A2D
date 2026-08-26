import type { AvatarModelV1, Part, Pseudo3DHeadData } from "@a2d/avatar-schema";
import { createTypedView, type LoadedA2DPackage } from "./packageLoader.js";
import { ParameterCore } from "./parameterCore.js";
import type { GpuTimingInfo } from "./gpuTiming.js";

type PartGpu = {
  part: Part;
  vao: WebGLVertexArrayObject;
  buffers: WebGLBuffer[];
  indexCount: number;
  indexType: number;
};
type DisjointTimerQueryExt = { TIME_ELAPSED_EXT: number; GPU_DISJOINT_EXT: number };
const MAX_VERTEX_INFLUENCES = 8;

const VERT = `#version 300 es
precision highp float;
precision highp int;
layout(location=0) in vec2 a_position;
layout(location=1) in vec2 a_uv;
layout(location=2) in float a_proxyZ;
layout(location=3) in uvec2 a_influenceRange;
uniform sampler2D u_parameters;
uniform sampler2D u_parameterDefs;
uniform sampler2D u_morphInfluences;
uniform ivec2 u_parameterTexSize;
uniform ivec2 u_influenceTexSize;
uniform int u_paramAngleX;
uniform int u_paramAngleY;
uniform int u_paramAngleZ;
uniform vec2 u_headPivot;
uniform float u_headDepthScale;
uniform float u_headPerspective;
uniform float u_headYawGain;
uniform float u_headPitchGain;
out vec2 v_uv;
float fetchScalar(sampler2D tex, ivec2 size, int index) {
  int x = index % size.x;
  int y = index / size.x;
  return texelFetch(tex, ivec2(x, y), 0).r;
}
vec4 fetchRecord(sampler2D tex, ivec2 size, int index) {
  int x = index % size.x;
  int y = index / size.x;
  return texelFetch(tex, ivec2(x, y), 0);
}
float normalizedParameter(int index) {
  if (index < 0) return 0.0;
  float value = fetchScalar(u_parameters, u_parameterTexSize, index);
  vec4 def = fetchRecord(u_parameterDefs, u_parameterTexSize, index);
  float minV = def.r;
  float maxV = def.g;
  float defaultV = def.b;
  if (value >= defaultV) {
    float denom = maxV - defaultV;
    return denom == 0.0 ? 0.0 : clamp((value-defaultV)/denom, 0.0, 1.0);
  } else {
    float denom = defaultV - minV;
    return denom == 0.0 ? 0.0 : clamp((value-defaultV)/denom, -1.0, 0.0);
  }
}
void main() {
  vec2 p = a_position;
  uint influenceCount = min(a_influenceRange.y, uint(${MAX_VERTEX_INFLUENCES}));
  for (uint i = 0u; i < uint(${MAX_VERTEX_INFLUENCES}); ++i) {
    if (i >= influenceCount) break;
    int recordIndex = int(a_influenceRange.x + i);
    vec4 rec = fetchRecord(u_morphInfluences, u_influenceTexSize, recordIndex);
    int parameterIndex = int(rec.r + 0.5);
    float n = normalizedParameter(parameterIndex);
    p += n * rec.a * rec.gb;
  }
  float angleX = u_paramAngleX >= 0 ? fetchScalar(u_parameters, u_parameterTexSize, u_paramAngleX) : 0.0;
  float angleY = u_paramAngleY >= 0 ? fetchScalar(u_parameters, u_parameterTexSize, u_paramAngleY) : 0.0;
  float angleZ = u_paramAngleZ >= 0 ? fetchScalar(u_parameters, u_parameterTexSize, u_paramAngleZ) : 0.0;
  vec2 local = p - u_headPivot;
  float z0 = a_proxyZ * u_headDepthScale;
  float yaw = radians(angleX * u_headYawGain);
  float pitch = radians(angleY * u_headPitchGain);
  float cy = cos(yaw);
  float sy = sin(yaw);
  float cp = cos(pitch);
  float sp = sin(pitch);
  float x1 = cy * local.x + sy * z0;
  float z1 = -sy * local.x + cy * z0;
  float y1 = cp * local.y - sp * z1;
  float z2 = sp * local.y + cp * z1;
  float depthDelta = z2 - z0;
  float persp = 1.0 / max(0.25, 1.0 + u_headPerspective * depthDelta);
  p = vec2(x1, y1) * persp + u_headPivot;
  float roll = radians(angleZ);
  float cr = cos(roll);
  float sr = sin(roll);
  local = p - u_headPivot;
  p = vec2(cr*local.x - sr*local.y, sr*local.x + cr*local.y) + u_headPivot;
  gl_Position = vec4(p.x * 2.0 - 1.0, 1.0 - p.y * 2.0, 0.0, 1.0);
  v_uv = a_uv;
}`;
const FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 outColor;
void main() { outColor = vec4(v_uv.x, 1.0-v_uv.y, 0.9, 1.0); }`;

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("createShader failed");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`shader compile failed: ${log}`);
  }
  return shader;
}
function makeProgram(gl: WebGL2RenderingContext): WebGLProgram {
  const vs = compile(gl, gl.VERTEX_SHADER, VERT);
  const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
  const program = gl.createProgram();
  if (!program) throw new Error("createProgram failed");
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`program link failed: ${log}`);
  }
  return program;
}
function textureSize(count: number): [number, number] {
  const width = Math.max(1, Math.min(1024, count));
  return [width, Math.max(1, Math.ceil(count / width))];
}
function uploadR32F(gl: WebGL2RenderingContext, data: Float32Array, size: [number, number]): WebGLTexture {
  const texture = gl.createTexture();
  if (!texture) throw new Error("texture allocation failed");
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const padded = new Float32Array(size[0] * size[1]);
  padded.set(data);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, size[0], size[1], 0, gl.RED, gl.FLOAT, padded);
  return texture;
}
function uploadRGBA32F(gl: WebGL2RenderingContext, data: Float32Array, recordCount: number): { texture: WebGLTexture; size: [number, number] } {
  const size = textureSize(recordCount);
  const texture = gl.createTexture();
  if (!texture) throw new Error("texture allocation failed");
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const padded = new Float32Array(size[0] * size[1] * 4);
  padded.set(data);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, size[0], size[1], 0, gl.RGBA, gl.FLOAT, padded);
  return { texture, size };
}
function sleep(ms: number): Promise<void> { return new Promise(resolve => setTimeout(resolve, ms)); }

export class WebGL2DeformationRenderer {
  readonly backend = "webgl2" as const;
  readonly gl: WebGL2RenderingContext;
  readonly model: AvatarModelV1;
  readonly parameters: ParameterCore;
  readonly gpuTiming: GpuTimingInfo;
  private readonly program: WebGLProgram;
  private readonly parts: PartGpu[] = [];
  private readonly parameterTexture: WebGLTexture;
  private readonly parameterDefTexture: WebGLTexture;
  private readonly influenceTexture: WebGLTexture;
  private readonly parameterTexSize: [number, number];
  private readonly influenceTexSize: [number, number];
  private readonly head: Pseudo3DHeadData;
  private readonly parameterIndices: { x: number; y: number; z: number };
  private readonly timerExt: DisjointTimerQueryExt | null;
  private readonly pendingQueries: WebGLQuery[] = [];
  private readonly gpuTimingSamples: number[] = [];
  private gpuTimingEnabled = false;

  constructor(canvas: HTMLCanvasElement, pkg: LoadedA2DPackage) {
    const gl = canvas.getContext("webgl2", { alpha: true, antialias: true });
    if (!gl) throw new Error("WebGL2 is unavailable");
    this.gl = gl;
    this.model = pkg.model;
    this.parameters = new ParameterCore(pkg.model.parameters);
    this.program = makeProgram(gl);
    this.timerExt = gl.getExtension("EXT_disjoint_timer_query_webgl2") as DisjointTimerQueryExt | null;
    this.gpuTiming = this.timerExt
      ? { supported: true, source: "webgl2-disjoint-timer-query" }
      : { supported: false, reason: "EXT_disjoint_timer_query_webgl2 is unavailable" };
    this.parameterTexSize = textureSize(Math.max(1, this.parameters.length));
    this.parameterTexture = uploadR32F(gl, this.parameters.values, this.parameterTexSize);
    const defs = new Float32Array(this.parameterTexSize[0] * this.parameterTexSize[1] * 4);
    pkg.model.parameters.forEach((parameter, index) => {
      defs[index * 4] = parameter.min;
      defs[index * 4 + 1] = parameter.max;
      defs[index * 4 + 2] = parameter.default;
    });
    this.parameterDefTexture = uploadRGBA32F(gl, defs, this.parameterTexSize[0] * this.parameterTexSize[1]).texture;
    const influenceRef = pkg.model.deformationBuffers?.morphInfluences?.view;
    let influenceFloatData = new Float32Array(4);
    let influenceCount = 1;
    if (influenceRef) {
      const source = pkg.buffers.get(influenceRef.buffer);
      if (!source) throw new Error(`missing influence buffer ${influenceRef.buffer}`);
      influenceCount = influenceRef.byteLength / 16;
      influenceFloatData = new Float32Array(influenceCount * 4);
      const view = new DataView(source, influenceRef.byteOffset, influenceRef.byteLength);
      for (let index = 0; index < influenceCount; index++) {
        const base = index * 16;
        influenceFloatData[index * 4] = view.getUint32(base, true);
        influenceFloatData[index * 4 + 1] = view.getFloat32(base + 4, true);
        influenceFloatData[index * 4 + 2] = view.getFloat32(base + 8, true);
        influenceFloatData[index * 4 + 3] = view.getFloat32(base + 12, true);
      }
    }
    const influence = uploadRGBA32F(gl, influenceFloatData, influenceCount);
    this.influenceTexture = influence.texture;
    this.influenceTexSize = influence.size;
    const headDef = pkg.model.deformers.find(deformer => deformer.type === "pseudo3d_head");
    const data = headDef?.data as Partial<Pseudo3DHeadData> | undefined;
    this.head = {
      pivot: data?.pivot ?? [0.5, 0.5], radius: data?.radius ?? [0.5, 0.6],
      depthScale: data?.depthScale ?? 0, perspective: data?.perspective ?? 0,
      yawGain: data?.yawGain ?? 1, pitchGain: data?.pitchGain ?? 1
    };
    const getIndex = (id: string) => this.parameters.indexById.get(id) ?? -1;
    this.parameterIndices = { x: getIndex("ParamAngleX"), y: getIndex("ParamAngleY"), z: getIndex("ParamAngleZ") };
    const sorted = [...pkg.model.parts].sort((a, b) => a.drawOrder - b.drawOrder);
    for (const part of sorted) this.parts.push(this.createPart(pkg, part));
  }

  private createPart(pkg: LoadedA2DPackage, part: Part): PartGpu {
    const { gl } = this;
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
    const vao = gl.createVertexArray();
    if (!vao) throw new Error("createVertexArray failed");
    gl.bindVertexArray(vao);
    const buffers: WebGLBuffer[] = [];
    const addFloat = (location: number, data: Float32Array, size: number): void => {
      const buffer = gl.createBuffer();
      if (!buffer) throw new Error("buffer allocation failed");
      buffers.push(buffer);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
    };
    addFloat(0, positions, 2); addFloat(1, uvs, 2); addFloat(2, proxyZ, 1);
    const rangeBuffer = gl.createBuffer();
    if (!rangeBuffer) throw new Error("buffer allocation failed");
    buffers.push(rangeBuffer);
    gl.bindBuffer(gl.ARRAY_BUFFER, rangeBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, ranges, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribIPointer(3, 2, gl.UNSIGNED_INT, 0, 0);
    const indexBuffer = gl.createBuffer();
    if (!indexBuffer) throw new Error("buffer allocation failed");
    buffers.push(indexBuffer);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    gl.bindVertexArray(null);
    return { part, vao, buffers, indexCount: indices.length, indexType: indices instanceof Uint32Array ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT };
  }

  setParameter(id: string, value: number): void { this.parameters.set(id, value); }
  setGpuTimingEnabled(enabled: boolean): void { this.gpuTimingEnabled = enabled && this.gpuTiming.supported; }
  async collectGpuTimings(): Promise<number[]> {
    if (this.timerExt) {
      const deadline = performance.now() + 5000;
      while (this.pendingQueries.length > 0 && performance.now() < deadline) {
        this.pollGpuQueries();
        if (this.pendingQueries.length > 0) await sleep(0);
      }
      if (this.pendingQueries.length > 0) {
        for (const query of this.pendingQueries.splice(0)) this.gl.deleteQuery(query);
      }
    }
    return this.gpuTimingSamples.splice(0, this.gpuTimingSamples.length);
  }
  private flushDirtyParameters(): void {
    const range = this.parameters.consumeDirtyRange();
    if (!range) return;
    const { gl } = this;
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.parameterTexture);
    let index = range.start;
    while (index < range.endExclusive) {
      const x = index % this.parameterTexSize[0];
      const y = Math.floor(index / this.parameterTexSize[0]);
      const count = Math.min(this.parameterTexSize[0] - x, range.endExclusive - index);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, x, y, count, 1, gl.RED, gl.FLOAT, this.parameters.values.subarray(index, index + count));
      index += count;
    }
  }
  private pollGpuQueries(): void {
    const ext = this.timerExt;
    if (!ext || this.pendingQueries.length === 0) return;
    const { gl } = this;
    if (Boolean(gl.getParameter(ext.GPU_DISJOINT_EXT))) {
      for (const query of this.pendingQueries.splice(0)) gl.deleteQuery(query);
      return;
    }
    while (this.pendingQueries.length > 0) {
      const query = this.pendingQueries[0];
      if (!Boolean(gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE))) break;
      const elapsedNs = Number(gl.getQueryParameter(query, gl.QUERY_RESULT));
      this.pendingQueries.shift();
      gl.deleteQuery(query);
      const elapsedMs = elapsedNs / 1_000_000;
      if (Number.isFinite(elapsedMs) && elapsedMs >= 0) this.gpuTimingSamples.push(elapsedMs);
    }
  }

  render(): number {
    const { gl } = this;
    const canvas = gl.canvas as HTMLCanvasElement;
    const dpr = globalThis.devicePixelRatio || 1;
    const width = Math.max(1, Math.floor(canvas.clientWidth * dpr));
    const height = Math.max(1, Math.floor(canvas.clientHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    this.pollGpuQueries();
    this.flushDirtyParameters();
    const ext = this.timerExt;
    let query: WebGLQuery | null = null;
    if (this.gpuTimingEnabled && ext) {
      query = gl.createQuery();
      if (query) gl.beginQuery(ext.TIME_ELAPSED_EXT, query);
    }
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.06, 0.06, 0.07, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.program);
    const loc = (name: string) => gl.getUniformLocation(this.program, name);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.parameterTexture); gl.uniform1i(loc("u_parameters"), 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.parameterDefTexture); gl.uniform1i(loc("u_parameterDefs"), 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, this.influenceTexture); gl.uniform1i(loc("u_morphInfluences"), 2);
    gl.uniform2i(loc("u_parameterTexSize"), this.parameterTexSize[0], this.parameterTexSize[1]);
    gl.uniform2i(loc("u_influenceTexSize"), this.influenceTexSize[0], this.influenceTexSize[1]);
    gl.uniform1i(loc("u_paramAngleX"), this.parameterIndices.x); gl.uniform1i(loc("u_paramAngleY"), this.parameterIndices.y); gl.uniform1i(loc("u_paramAngleZ"), this.parameterIndices.z);
    gl.uniform2f(loc("u_headPivot"), this.head.pivot[0], this.head.pivot[1]);
    gl.uniform1f(loc("u_headDepthScale"), this.head.depthScale); gl.uniform1f(loc("u_headPerspective"), this.head.perspective);
    gl.uniform1f(loc("u_headYawGain"), this.head.yawGain); gl.uniform1f(loc("u_headPitchGain"), this.head.pitchGain);
    let drawCalls = 0;
    for (const part of this.parts) {
      gl.bindVertexArray(part.vao);
      gl.drawElements(gl.TRIANGLES, part.indexCount, part.indexType, 0);
      drawCalls++;
    }
    gl.bindVertexArray(null);
    if (query && ext) {
      gl.endQuery(ext.TIME_ELAPSED_EXT);
      this.pendingQueries.push(query);
    }
    this.pollGpuQueries();
    return drawCalls;
  }

  destroy(): void {
    this.gpuTimingEnabled = false;
    const { gl } = this;
    for (const query of this.pendingQueries.splice(0)) gl.deleteQuery(query);
    for (const part of this.parts) {
      gl.deleteVertexArray(part.vao);
      for (const buffer of part.buffers) gl.deleteBuffer(buffer);
    }
    gl.deleteTexture(this.parameterTexture);
    gl.deleteTexture(this.parameterDefTexture);
    gl.deleteTexture(this.influenceTexture);
    gl.deleteProgram(this.program);
  }
}
