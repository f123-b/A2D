import test from "node:test";
import assert from "node:assert/strict";
import { ParameterCore } from "./parameterCore.js";
import { FixedStepPhysics, SpringChain } from "./physics.js";

function makeRuntime() {
  const parameters = new ParameterCore([
    { id: "ParamAngleX", min: -30, max: 30, default: 0 },
    { id: "ParamHairX", min: -1, max: 1, default: 0 }
  ]);

  const chain = new SpringChain({
    id: "hair",
    nodeCount: 5,
    segmentLength: 0.08,
    root: { x: 0.5, y: 0.2 },
    gravity: { x: 0, y: 0.8 },
    damping: 0.08,
    stiffness: 0.95,
    maxDisplacement: 1.0,
    inputBindings: [
      { parameterId: "ParamAngleX", axis: "x", gain: 0.004 }
    ],
    outputBindings: [
      {
        parameterId: "ParamHairX",
        axis: "x",
        source: "tip",
        gain: 2.0,
        min: -1,
        max: 1
      }
    ]
  });

  return {
    parameters,
    physics: new FixedStepPhysics([chain], {
      physicsHz: 120,
      maxFrameDt: 0.1,
      maxSubSteps: 12
    }),
    chain
  };
}

function simulate(renderHz: number): number {
  const { parameters, physics } = makeRuntime();
  const dt = 1 / renderHz;

  for (let frame = 0; frame < renderHz * 2; frame++) {
    const t = frame * dt;
    parameters.set("ParamAngleX", t < 0.5 ? 0 : 20);
    physics.update(dt, parameters);
  }

  return parameters.get("ParamHairX");
}

test("fixed-step physics converges across render rates", () => {
  const a = simulate(30);
  const b = simulate(60);
  const c = simulate(120);

  assert.ok(Math.abs(a - b) <= 1e-3, `${a} vs ${b}`);
  assert.ok(Math.abs(b - c) <= 1e-3, `${b} vs ${c}`);
  assert.ok(Math.abs(a - c) <= 1e-3, `${a} vs ${c}`);
});

test("invalid large frame dt is clamped and bounded", () => {
  const { parameters, physics, chain } = makeRuntime();
  parameters.set("ParamAngleX", 30);
  const stats = physics.update(10, parameters);

  assert.ok(stats.subSteps <= 12);
  assert.ok(Number.isFinite(parameters.get("ParamHairX")));

  for (let i = 0; i < chain.x.length; i++) {
    assert.ok(Number.isFinite(chain.x[i]));
    assert.ok(Number.isFinite(chain.y[i]));
  }
});

test("long-run state remains finite", () => {
  const { parameters, physics, chain } = makeRuntime();

  for (let i = 0; i < 120 * 60; i++) {
    const t = i / 120;
    parameters.set("ParamAngleX", Math.sin(t * 2.3) * 25);
    physics.update(1 / 120, parameters);
  }

  assert.ok(Number.isFinite(parameters.get("ParamHairX")));
  for (let i = 0; i < chain.x.length; i++) {
    assert.ok(Number.isFinite(chain.x[i]));
    assert.ok(Number.isFinite(chain.y[i]));
  }
});
