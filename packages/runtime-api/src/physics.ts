import { ParameterCore } from "./parameterCore.js";

export interface Vec2 {
  x: number;
  y: number;
}

export interface SpringChainInputBinding {
  parameterId: string;
  axis: "x" | "y";
  gain: number;
}

export interface SpringChainOutputBinding {
  parameterId: string;
  axis: "x" | "y";
  source: "tip" | "average";
  gain: number;
  min: number;
  max: number;
}

export interface SpringChainConfig {
  id: string;
  nodeCount: number;
  segmentLength: number;
  gravity: Vec2;
  damping: number;
  stiffness: number;
  root: Vec2;
  inputBindings?: SpringChainInputBinding[];
  outputBindings?: SpringChainOutputBinding[];
  maxDisplacement?: number;
}

export interface PhysicsStepStats {
  subSteps: number;
  droppedTimeSeconds: number;
}

function finite(v: number): boolean {
  return Number.isFinite(v);
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

export class SpringChain {
  readonly config: SpringChainConfig;
  readonly x: Float32Array;
  readonly y: Float32Array;
  readonly prevX: Float32Array;
  readonly prevY: Float32Array;
  readonly restLength: Float32Array;

  private rootX: number;
  private rootY: number;
  private previousRootX: number;
  private previousRootY: number;

  constructor(config: SpringChainConfig) {
    if (!Number.isInteger(config.nodeCount) || config.nodeCount < 2) {
      throw new Error(`spring chain ${config.id}: nodeCount must be >= 2`);
    }
    if (!(config.segmentLength > 0)) {
      throw new Error(`spring chain ${config.id}: segmentLength must be > 0`);
    }

    this.config = {
      ...config,
      damping: clamp(config.damping, 0, 1),
      stiffness: clamp(config.stiffness, 0, 1),
      maxDisplacement: config.maxDisplacement ?? config.segmentLength * config.nodeCount * 2
    };

    this.x = new Float32Array(config.nodeCount);
    this.y = new Float32Array(config.nodeCount);
    this.prevX = new Float32Array(config.nodeCount);
    this.prevY = new Float32Array(config.nodeCount);
    this.restLength = new Float32Array(config.nodeCount - 1);

    this.rootX = config.root.x;
    this.rootY = config.root.y;
    this.previousRootX = this.rootX;
    this.previousRootY = this.rootY;

    this.reset();
  }

  reset(): void {
    const { segmentLength } = this.config;
    for (let i = 0; i < this.x.length; i++) {
      this.x[i] = this.rootX;
      this.y[i] = this.rootY + i * segmentLength;
      this.prevX[i] = this.x[i];
      this.prevY[i] = this.y[i];
      if (i < this.restLength.length) this.restLength[i] = segmentLength;
    }
  }

  step(dt: number, parameters: ParameterCore): void {
    if (!(dt > 0) || !finite(dt)) return;

    this.previousRootX = this.rootX;
    this.previousRootY = this.rootY;

    let drivenX = this.config.root.x;
    let drivenY = this.config.root.y;

    for (const binding of this.config.inputBindings ?? []) {
      const value = parameters.get(binding.parameterId);
      const delta = value * binding.gain;
      if (binding.axis === "x") drivenX += delta;
      else drivenY += delta;
    }

    this.rootX = drivenX;
    this.rootY = drivenY;

    const rootVelX = this.rootX - this.previousRootX;
    const rootVelY = this.rootY - this.previousRootY;
    const dampingScale = 1 - this.config.damping;
    const gravityX = this.config.gravity.x * dt * dt;
    const gravityY = this.config.gravity.y * dt * dt;

    this.x[0] = this.rootX;
    this.y[0] = this.rootY;
    this.prevX[0] = this.rootX;
    this.prevY[0] = this.rootY;

    for (let i = 1; i < this.x.length; i++) {
      const cx = this.x[i];
      const cy = this.y[i];

      let vx = (cx - this.prevX[i]) * dampingScale - rootVelX;
      let vy = (cy - this.prevY[i]) * dampingScale - rootVelY;

      this.prevX[i] = cx;
      this.prevY[i] = cy;

      this.x[i] = cx + vx + gravityX;
      this.y[i] = cy + vy + gravityY;
    }

    for (let iteration = 0; iteration < 4; iteration++) {
      this.x[0] = this.rootX;
      this.y[0] = this.rootY;

      for (let i = 1; i < this.x.length; i++) {
        const parent = i - 1;
        let dx = this.x[i] - this.x[parent];
        let dy = this.y[i] - this.y[parent];
        let distance = Math.hypot(dx, dy);

        if (!finite(distance) || distance < 1e-6) {
          dx = 0;
          dy = this.restLength[parent];
          distance = this.restLength[parent];
        }

        const target = this.restLength[parent];
        const error = (distance - target) / distance;
        const correction = error * this.config.stiffness;

        if (parent === 0) {
          this.x[i] -= dx * correction;
          this.y[i] -= dy * correction;
        } else {
          const half = 0.5 * correction;
          this.x[parent] += dx * half;
          this.y[parent] += dy * half;
          this.x[i] -= dx * half;
          this.y[i] -= dy * half;
        }
      }
    }

    this.enforceBoundsOrReset();
  }

  writeOutputs(parameters: ParameterCore): void {
    for (const binding of this.config.outputBindings ?? []) {
      let value = 0;

      if (binding.source === "tip") {
        const i = this.x.length - 1;
        value = binding.axis === "x"
          ? this.x[i] - this.rootX
          : this.y[i] - this.rootY;
      } else {
        let sum = 0;
        for (let i = 1; i < this.x.length; i++) {
          sum += binding.axis === "x"
            ? this.x[i] - this.rootX
            : this.y[i] - this.rootY;
        }
        value = sum / Math.max(1, this.x.length - 1);
      }

      value = clamp(value * binding.gain, binding.min, binding.max);
      if (!finite(value)) value = 0;
      parameters.set(binding.parameterId, value);
    }
  }

  private enforceBoundsOrReset(): void {
    const maxD = this.config.maxDisplacement ?? 1;

    for (let i = 0; i < this.x.length; i++) {
      if (!finite(this.x[i]) || !finite(this.y[i])) {
        this.reset();
        return;
      }

      const dx = this.x[i] - this.rootX;
      const dy = this.y[i] - this.rootY;
      const d = Math.hypot(dx, dy);

      if (!finite(d) || d > maxD) {
        this.reset();
        return;
      }
    }
  }
}

export class FixedStepPhysics {
  readonly fixedDt: number;
  readonly maxFrameDt: number;
  readonly maxSubSteps: number;
  readonly chains: readonly SpringChain[];

  private accumulator = 0;

  constructor(
    chains: readonly SpringChain[],
    options?: {
      physicsHz?: number;
      maxFrameDt?: number;
      maxSubSteps?: number;
    }
  ) {
    const hz = options?.physicsHz ?? 120;
    if (!(hz > 0)) throw new Error("physicsHz must be > 0");
    this.fixedDt = 1 / hz;
    this.maxFrameDt = options?.maxFrameDt ?? 0.1;
    this.maxSubSteps = options?.maxSubSteps ?? 12;
    this.chains = chains;
  }

  reset(): void {
    this.accumulator = 0;
    for (const chain of this.chains) chain.reset();
  }

  update(frameDt: number, parameters: ParameterCore): PhysicsStepStats {
    const clampedFrameDt = clamp(finite(frameDt) ? frameDt : 0, 0, this.maxFrameDt);
    this.accumulator += clampedFrameDt;

    let subSteps = 0;
    while (this.accumulator + 1e-12 >= this.fixedDt && subSteps < this.maxSubSteps) {
      for (const chain of this.chains) chain.step(this.fixedDt, parameters);
      this.accumulator -= this.fixedDt;
      subSteps++;
    }

    let droppedTimeSeconds = 0;
    if (this.accumulator >= this.fixedDt) {
      droppedTimeSeconds = this.accumulator;
      this.accumulator = 0;
    }

    for (const chain of this.chains) chain.writeOutputs(parameters);

    return { subSteps, droppedTimeSeconds };
  }
}
