export type ComponentType = "f32" | "u16" | "u32";

export interface BufferDescriptor { id: string; uri: string; byteLength: number; }
export interface BufferView { buffer: string; byteOffset: number; byteLength: number; componentType: ComponentType; count: number; stride?: number; }
export interface StructuredBufferView { buffer: string; byteOffset: number; byteLength: number; count: number; stride: number; }
export interface Parameter { id: string; min: number; max: number; default: number; }

export type PartSemantic =
  | "face" | "eye_l" | "eye_r" | "iris_l" | "iris_r" | "mouth"
  | "hair_front" | "hair_side" | "hair_back" | "body"
  | "arm_l" | "arm_r" | "cloth" | "accessory" | "other";

export type TextureFormatV1 = "rgba8" | "png" | "webp";
export type TextureAlphaModeV1 = "straight" | "premultiplied";
export type TextureFilterV1 = "linear" | "nearest";

export interface TextureResourceV1 {
  id: string;
  uri: string;
  byteLength: number;
  format: TextureFormatV1;
  width?: number;
  height?: number;
  alphaMode?: TextureAlphaModeV1;
  filter?: TextureFilterV1;
}

export interface PartMaterialV1 {
  textureId?: string;
  opacity?: number;
  blendMode?: "normal";
}

export interface ClipMaskV1 {
  sources: string[];
  mode: "inside" | "outside";
}

export interface MeshRef {
  positions: BufferView;
  uvs: BufferView;
  indices: BufferView;
  proxyZ?: BufferView;
  influenceRanges?: BufferView;
}

export interface Part {
  id: string;
  name?: string;
  semantic: PartSemantic;
  parent?: string | null;
  drawOrder: number;
  /** @deprecated R8A uses material.textureId. */
  textureAtlas?: string | null;
  material?: PartMaterialV1;
  clip?: ClipMaskV1;
  mesh: MeshRef;
}

export type DeformerType = "warp" | "rotation" | "morph" | "pseudo3d_head";
export interface ParameterBinding { parameterId: string; scale?: number; bias?: number; }
export interface Pseudo3DHeadData { pivot: [number, number]; radius: [number, number]; depthScale: number; perspective: number; yawGain: number; pitchGain: number; }
export interface Deformer { id: string; type: DeformerType; parent?: string | null; targets: string[]; parameterBindings?: ParameterBinding[]; data?: Record<string, unknown> | Pseudo3DHeadData; }
export interface MorphInfluenceBufferRef { view: StructuredBufferView; strideBytes: 16; }
export interface DeformationBuffers { morphInfluences?: MorphInfluenceBufferRef; }

export interface PhysicsInputBindingV1 { parameterId: string; axis: "x" | "y"; gain: number; }
export interface PhysicsOutputBindingV1 { parameterId: string; axis: "x" | "y"; source: "tip" | "average"; gain: number; min: number; max: number; }
export interface SpringChainPhysics {
  id: string; type: "spring_chain"; nodeCount: number; segmentLength: number;
  root: [number, number]; gravity: [number, number]; damping: number; stiffness: number;
  inputBindings?: PhysicsInputBindingV1[]; outputBindings?: PhysicsOutputBindingV1[]; maxDisplacement?: number;
}

export type ExpressionBindingModeV1 = "set" | "add";
export interface ExpressionBindingV1 {
  parameterId: string;
  mode: ExpressionBindingModeV1;
  value: number;
}
export interface ExpressionPresetV1 {
  id: string;
  label?: string;
  bindings: ExpressionBindingV1[];
}

export interface AvatarModelV1 {
  formatVersion: 1;
  id: string;
  name?: string;
  canvas: { width: number; height: number };
  buffers: BufferDescriptor[];
  textures?: TextureResourceV1[];
  parameters: Parameter[];
  parts: Part[];
  deformers: Deformer[];
  deformationBuffers?: DeformationBuffers;
  physics?: SpringChainPhysics[];
  expressions?: ExpressionPresetV1[];
}

export const STANDARD_PARAMETER_IDS = [
  "ParamAngleX", "ParamAngleY", "ParamAngleZ",
  "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ", "ParamBreath",
  "ParamEyeLOpen", "ParamEyeROpen", "ParamEyeBallX", "ParamEyeBallY",
  "ParamMouthOpenY", "ParamMouthForm",
  "ParamBrowLY", "ParamBrowRY", "ParamBrowLAngle", "ParamBrowRAngle"
] as const;
export type StandardParameterId = typeof STANDARD_PARAMETER_IDS[number];
