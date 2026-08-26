export interface TrackingFrame {
  timestampMs: number;
  head: { x: number; y: number; z: number };
  eyes: {
    leftOpen: number;
    rightOpen: number;
    gazeX: number;
    gazeY: number;
  };
  mouth: {
    open: number;
    form: number;
  };
  brows?: {
    leftY: number;
    rightY: number;
    leftAngle: number;
    rightAngle: number;
  };
}

export interface TrackingAdapter {
  readonly id: string;
  start(): Promise<void>;
  stop(): Promise<void>;
  readLatest(): TrackingFrame | null;
}
