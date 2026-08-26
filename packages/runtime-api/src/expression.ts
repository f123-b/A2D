import type { AvatarModelV1, ExpressionPresetV1 } from "@a2d/avatar-schema";
import { ParameterCore } from "./parameterCore.js";

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function findExpressionPreset(
  model: AvatarModelV1,
  id: string
): ExpressionPresetV1 {
  const preset = model.expressions?.find(value => value.id === id);
  if (!preset) throw new Error(`unknown expression preset: ${id}`);
  return preset;
}

/**
 * Applies one expression on top of the current parameter frame.
 *
 * `set` blends the current value toward an absolute target.
 * `add` adds a weighted offset. ParameterCore performs final range clamping.
 *
 * Runtime order is expected to be:
 * tracking -> animation -> expression -> physics -> GPU upload.
 */
export function applyExpressionPreset(
  parameters: ParameterCore,
  preset: ExpressionPresetV1,
  strength = 1
): void {
  const t = clamp01(strength);
  if (t === 0) return;

  for (const binding of preset.bindings) {
    const current = parameters.get(binding.parameterId);
    const next = binding.mode === "set"
      ? current + (binding.value - current) * t
      : current + binding.value * t;
    parameters.set(binding.parameterId, next);
  }
}
