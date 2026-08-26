export type GpuTimingSource = "webgpu-timestamp-query" | "webgl2-disjoint-timer-query";

export interface GpuTimingInfo {
  supported: boolean;
  source?: GpuTimingSource;
  reason?: string;
}

export interface GpuTimingController {
  readonly gpuTiming: GpuTimingInfo;
  setGpuTimingEnabled(enabled: boolean): void;
  collectGpuTimings(): Promise<number[]>;
}
