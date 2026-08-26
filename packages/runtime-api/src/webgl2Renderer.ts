import type { AvatarModelV1, Part } from "@a2d/avatar-schema";
import { createTypedView, type LoadedA2DPackage } from "./packageLoader.js";

type PartGpu = {
  part: Part;
  vao: WebGLVertexArrayObject;
  positionBuffer: WebGLBuffer;
  uvBuffer: WebGLBuffer;
  indexBuffer: WebGLBuffer;
  indexCount: number;
  indexType: number;
};

const VERT = `#version 300 es
precision highp float;
layout(location=0) in vec2 a_position;
layout(location=1) in vec2 a_uv;
uniform vec2 u_canvas;
uniform vec2 u_viewport;
uniform float u_angleX;
out vec2 v_uv;

void main() {
  float xNorm = (a_position.x / max(u_canvas.x, 1.0)) * 2.0 - 1.0;
  float head = radians(u_angleX);
  float pseudoDepth = sqrt(max(0.0, 1.0 - min(1.0, xNorm*xNorm)));
  vec2 p = a_position;
  p.x += sin(head) * pseudoDepth * u_canvas.x * 0.03;

  vec2 ndc = vec2(
    (p.x / u_canvas.x) * 2.0 - 1.0,
    1.0 - (p.y / u_canvas.y) * 2.0
  );
  gl_Position = vec4(ndc, 0.0, 1.0);
  v_uv = a_uv;
}`;

const FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 outColor;
void main() {
  outColor = vec4(v_uv.x, 1.0 - v_uv.y, 0.85, 1.0);
}`;

function shader(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const s = gl.createShader(type);
  if (!s) throw new Error("createShader failed");
  gl.shaderSource(s, source);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(s);
    gl.deleteShader(s);
    throw new Error(`shader compile failed: ${log}`);
  }
  return s;
}

function program(gl: WebGL2RenderingContext): WebGLProgram {
  const vs = shader(gl, gl.VERTEX_SHADER, VERT);
  const fs = shader(gl, gl.FRAGMENT_SHADER, FRAG);
  const p = gl.createProgram();
  if (!p) throw new Error("createProgram failed");
  gl.attachShader(p, vs);
  gl.attachShader(p, fs);
  gl.linkProgram(p);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(p);
    gl.deleteProgram(p);
    throw new Error(`program link failed: ${log}`);
  }
  return p;
}

export class WebGL2ReferenceRenderer {
  readonly gl: WebGL2RenderingContext;
  readonly model: AvatarModelV1;

  private readonly program: WebGLProgram;
  private readonly parts: PartGpu[] = [];
  private readonly uCanvas: WebGLUniformLocation | null;
  private readonly uViewport: WebGLUniformLocation | null;
  private readonly uAngleX: WebGLUniformLocation | null;

  constructor(
    canvas: HTMLCanvasElement,
    pkg: LoadedA2DPackage
  ) {
    const gl = canvas.getContext("webgl2", {
      alpha: true,
      antialias: true,
      premultipliedAlpha: true
    });
    if (!gl) throw new Error("WebGL2 is not available");
    this.gl = gl;
    this.model = pkg.model;
    this.program = program(gl);
    this.uCanvas = gl.getUniformLocation(this.program, "u_canvas");
    this.uViewport = gl.getUniformLocation(this.program, "u_viewport");
    this.uAngleX = gl.getUniformLocation(this.program, "u_angleX");

    const sorted = [...pkg.model.parts].sort((a, b) => a.drawOrder - b.drawOrder);
    for (const part of sorted) {
      const positions = createTypedView(pkg.buffers, part.mesh.positions);
      const uvs = createTypedView(pkg.buffers, part.mesh.uvs);
      const indices = createTypedView(pkg.buffers, part.mesh.indices);

      if (!(positions instanceof Float32Array)) throw new Error(`${part.id}: positions must be f32`);
      if (!(uvs instanceof Float32Array)) throw new Error(`${part.id}: uvs must be f32`);
      if (!(indices instanceof Uint16Array || indices instanceof Uint32Array)) {
        throw new Error(`${part.id}: indices must be u16/u32`);
      }

      const vao = gl.createVertexArray();
      const positionBuffer = gl.createBuffer();
      const uvBuffer = gl.createBuffer();
      const indexBuffer = gl.createBuffer();
      if (!vao || !positionBuffer || !uvBuffer || !indexBuffer) throw new Error("GPU resource allocation failed");

      gl.bindVertexArray(vao);

      gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

      gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, uvs, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 0, 0);

      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);

      this.parts.push({
        part, vao, positionBuffer, uvBuffer, indexBuffer,
        indexCount: indices.length,
        indexType: indices instanceof Uint32Array ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT
      });
    }

    gl.bindVertexArray(null);
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
  }

  render(angleX = 0): number {
    const { gl } = this;
    const canvas = gl.canvas as HTMLCanvasElement;
    const width = Math.max(1, Math.floor(canvas.clientWidth * devicePixelRatio));
    const height = Math.max(1, Math.floor(canvas.clientHeight * devicePixelRatio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.07, 0.07, 0.08, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(this.program);
    gl.uniform2f(this.uCanvas, this.model.canvas.width, this.model.canvas.height);
    gl.uniform2f(this.uViewport, canvas.width, canvas.height);
    gl.uniform1f(this.uAngleX, angleX);

    let drawCalls = 0;
    for (const gpu of this.parts) {
      gl.bindVertexArray(gpu.vao);
      gl.drawElements(gl.TRIANGLES, gpu.indexCount, gpu.indexType, 0);
      drawCalls++;
    }
    gl.bindVertexArray(null);
    return drawCalls;
  }

  destroy(): void {
    const { gl } = this;
    for (const gpu of this.parts) {
      gl.deleteVertexArray(gpu.vao);
      gl.deleteBuffer(gpu.positionBuffer);
      gl.deleteBuffer(gpu.uvBuffer);
      gl.deleteBuffer(gpu.indexBuffer);
    }
    gl.deleteProgram(this.program);
    this.parts.length = 0;
  }
}
