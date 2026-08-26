import type {
  AvatarModelV1,
  BufferDescriptor,
  BufferView,
  StructuredBufferView
} from "@a2d/avatar-schema";

export interface LoadedA2DPackage {
  manifest: A2DManifestV1;
  model: AvatarModelV1;
  buffers: Map<string, ArrayBuffer>;
}

export interface A2DManifestV1 {
  containerVersion: 1;
  model: string;
  entryBuffers: string[];
}

export interface ZipReader {
  readText(path: string): Promise<string>;
  readArrayBuffer(path: string): Promise<ArrayBuffer>;
  has(path: string): boolean;
}

const COMPONENT_SIZE: Record<BufferView["componentType"], number> = {
  f32: 4,
  u16: 2,
  u32: 4
};

export class A2DPackageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "A2DPackageError";
  }
}

function assertInt(name: string, value: unknown, min = 0): asserts value is number {
  if (!Number.isInteger(value) || Number(value) < min) {
    throw new A2DPackageError(`${name} must be an integer >= ${min}`);
  }
}

function validateManifest(value: unknown): A2DManifestV1 {
  if (!value || typeof value !== "object") throw new A2DPackageError("manifest.json must be an object");
  const m = value as Partial<A2DManifestV1>;
  if (m.containerVersion !== 1) throw new A2DPackageError(`unsupported containerVersion: ${String(m.containerVersion)}`);
  if (typeof m.model !== "string" || !m.model) throw new A2DPackageError("manifest.model is required");
  if (!Array.isArray(m.entryBuffers) || m.entryBuffers.some(v => typeof v !== "string")) {
    throw new A2DPackageError("manifest.entryBuffers must be string[]");
  }
  return m as A2DManifestV1;
}

function validateBufferView(
  view: BufferView,
  descriptor: BufferDescriptor,
  label: string
): void {
  assertInt(`${label}.byteOffset`, view.byteOffset);
  assertInt(`${label}.byteLength`, view.byteLength);
  assertInt(`${label}.count`, view.count);
  if (view.byteOffset % 4 !== 0) {
    throw new A2DPackageError(`${label}.byteOffset must be 4-byte aligned`);
  }

  const componentSize = COMPONENT_SIZE[view.componentType];
  if (!componentSize) throw new A2DPackageError(`${label}.componentType is invalid`);

  if (view.byteOffset + view.byteLength > descriptor.byteLength) {
    throw new A2DPackageError(`${label} exceeds buffer ${descriptor.id}`);
  }

  const stride = view.stride ?? componentSize;
  if (stride < componentSize) throw new A2DPackageError(`${label}.stride is smaller than component size`);

  if (view.byteLength === 0 && view.count > 0) {
    throw new A2DPackageError(`${label} has count > 0 but zero byteLength`);
  }
}

function validateStructuredBufferView(
  view: StructuredBufferView,
  descriptor: BufferDescriptor,
  label: string
): void {
  assertInt(`${label}.byteOffset`, view.byteOffset);
  assertInt(`${label}.byteLength`, view.byteLength);
  assertInt(`${label}.count`, view.count);
  assertInt(`${label}.stride`, view.stride, 1);

  if (view.byteOffset % 4 !== 0) {
    throw new A2DPackageError(`${label}.byteOffset must be 4-byte aligned`);
  }
  if (view.stride % 4 !== 0) {
    throw new A2DPackageError(`${label}.stride must be 4-byte aligned`);
  }
  if (view.byteOffset + view.byteLength > descriptor.byteLength) {
    throw new A2DPackageError(`${label} exceeds buffer ${descriptor.id}`);
  }
  if (view.count * view.stride > view.byteLength) {
    throw new A2DPackageError(`${label} count*stride exceeds byteLength`);
  }
}

function validateModel(model: AvatarModelV1): void {
  if (model.formatVersion !== 1) throw new A2DPackageError(`unsupported formatVersion: ${model.formatVersion}`);
  if (!model.id) throw new A2DPackageError("model.id is required");
  assertInt("canvas.width", model.canvas?.width, 1);
  assertInt("canvas.height", model.canvas?.height, 1);

  const bufferMap = new Map(model.buffers.map(b => [b.id, b]));
  if (bufferMap.size !== model.buffers.length) throw new A2DPackageError("buffer ids must be unique");

  const parameterIds = new Set<string>();
  for (const p of model.parameters) {
    if (parameterIds.has(p.id)) throw new A2DPackageError(`duplicate parameter id: ${p.id}`);
    parameterIds.add(p.id);
    if (!(p.min <= p.default && p.default <= p.max)) {
      throw new A2DPackageError(`parameter default out of range: ${p.id}`);
    }
  }

  const partIds = new Set<string>();
  for (const part of model.parts) {
    if (partIds.has(part.id)) throw new A2DPackageError(`duplicate part id: ${part.id}`);
    partIds.add(part.id);
    for (const [kind, view] of Object.entries(part.mesh)) {
      const desc = bufferMap.get(view.buffer);
      if (!desc) throw new A2DPackageError(`part ${part.id} ${kind} references unknown buffer ${view.buffer}`);
      validateBufferView(view, desc, `part.${part.id}.mesh.${kind}`);
    }
  }

  const morphInfluences = model.deformationBuffers?.morphInfluences;
  if (morphInfluences) {
    if (morphInfluences.strideBytes !== 16 || morphInfluences.view.stride !== 16) {
      throw new A2DPackageError("morph influence stride must be 16 bytes in Avatar IR v1");
    }
    const desc = bufferMap.get(morphInfluences.view.buffer);
    if (!desc) {
      throw new A2DPackageError(
        `morph influences reference unknown buffer ${morphInfluences.view.buffer}`
      );
    }
    validateStructuredBufferView(
      morphInfluences.view,
      desc,
      "deformationBuffers.morphInfluences.view"
    );
  }

  const physicsIds = new Set<string>();
  for (const physics of model.physics ?? []) {
    if (physicsIds.has(physics.id)) {
      throw new A2DPackageError(`duplicate physics id: ${physics.id}`);
    }
    physicsIds.add(physics.id);

    if (!Number.isInteger(physics.nodeCount) || physics.nodeCount < 2 || physics.nodeCount > 64) {
      throw new A2DPackageError(`physics ${physics.id}: nodeCount must be 2..64`);
    }
    if (!(physics.segmentLength > 0)) {
      throw new A2DPackageError(`physics ${physics.id}: segmentLength must be > 0`);
    }
    if (!(physics.damping >= 0 && physics.damping <= 1)) {
      throw new A2DPackageError(`physics ${physics.id}: damping must be 0..1`);
    }
    if (!(physics.stiffness >= 0 && physics.stiffness <= 1)) {
      throw new A2DPackageError(`physics ${physics.id}: stiffness must be 0..1`);
    }

    for (const binding of physics.inputBindings ?? []) {
      if (!parameterIds.has(binding.parameterId)) {
        throw new A2DPackageError(
          `physics ${physics.id} input references unknown parameter ${binding.parameterId}`
        );
      }
    }

    for (const binding of physics.outputBindings ?? []) {
      if (!parameterIds.has(binding.parameterId)) {
        throw new A2DPackageError(
          `physics ${physics.id} output references unknown parameter ${binding.parameterId}`
        );
      }
      if (binding.min > binding.max) {
        throw new A2DPackageError(
          `physics ${physics.id} output ${binding.parameterId}: min > max`
        );
      }
    }
  }

  for (const d of model.deformers) {
    for (const target of d.targets) {
      if (!partIds.has(target)) throw new A2DPackageError(`deformer ${d.id} targets unknown part ${target}`);
    }
    for (const binding of d.parameterBindings ?? []) {
      if (!parameterIds.has(binding.parameterId)) {
        throw new A2DPackageError(`deformer ${d.id} references unknown parameter ${binding.parameterId}`);
      }
    }
  }
}

export async function loadA2DFromZip(reader: ZipReader): Promise<LoadedA2DPackage> {
  if (!reader.has("manifest.json")) throw new A2DPackageError("manifest.json missing");
  const manifest = validateManifest(JSON.parse(await reader.readText("manifest.json")));

  if (!reader.has(manifest.model)) throw new A2DPackageError(`${manifest.model} missing`);
  const model = JSON.parse(await reader.readText(manifest.model)) as AvatarModelV1;
  validateModel(model);

  const buffers = new Map<string, ArrayBuffer>();
  for (const descriptor of model.buffers) {
    if (!reader.has(descriptor.uri)) throw new A2DPackageError(`${descriptor.uri} missing`);
    const bytes = await reader.readArrayBuffer(descriptor.uri);
    if (bytes.byteLength !== descriptor.byteLength) {
      throw new A2DPackageError(
        `buffer length mismatch for ${descriptor.id}: expected ${descriptor.byteLength}, got ${bytes.byteLength}`
      );
    }
    buffers.set(descriptor.id, bytes);
  }

  return { manifest, model, buffers };
}

export function createTypedView(
  buffers: Map<string, ArrayBuffer>,
  view: BufferView
): Float32Array | Uint16Array | Uint32Array {
  const buffer = buffers.get(view.buffer);
  if (!buffer) throw new A2DPackageError(`buffer not loaded: ${view.buffer}`);

  const scalarCount = view.byteLength / COMPONENT_SIZE[view.componentType];
  if (!Number.isInteger(scalarCount)) throw new A2DPackageError("buffer view byteLength is not component aligned");

  switch (view.componentType) {
    case "f32":
      return new Float32Array(buffer, view.byteOffset, scalarCount);
    case "u16":
      return new Uint16Array(buffer, view.byteOffset, scalarCount);
    case "u32":
      return new Uint32Array(buffer, view.byteOffset, scalarCount);
  }
}
