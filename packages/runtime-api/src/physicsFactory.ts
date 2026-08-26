import type { AvatarModelV1, SpringChainPhysics } from "@a2d/avatar-schema";
import { FixedStepPhysics, SpringChain, type SpringChainConfig } from "./physics.js";

export function springChainConfigFromIR(ir: SpringChainPhysics): SpringChainConfig {
  return {
    id: ir.id,
    nodeCount: ir.nodeCount,
    segmentLength: ir.segmentLength,
    root: { x: ir.root[0], y: ir.root[1] },
    gravity: { x: ir.gravity[0], y: ir.gravity[1] },
    damping: ir.damping,
    stiffness: ir.stiffness,
    maxDisplacement: ir.maxDisplacement,
    inputBindings: ir.inputBindings?.map(v => ({ ...v })),
    outputBindings: ir.outputBindings?.map(v => ({ ...v }))
  };
}

export function createPhysicsFromModel(
  model: AvatarModelV1,
  options?: {
    physicsHz?: number;
    maxFrameDt?: number;
    maxSubSteps?: number;
  }
): FixedStepPhysics {
  const chains = (model.physics ?? []).map(
    chain => new SpringChain(springChainConfigFromIR(chain))
  );
  return new FixedStepPhysics(chains, options);
}
