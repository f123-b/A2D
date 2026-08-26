export interface Distribution {
  count: number;
  min: number;
  max: number;
  mean: number;
  p50: number;
  p95: number;
  p99: number;
}

function quantileSorted(sorted: readonly number[], q: number): number {
  if (sorted.length === 0) return 0;
  const position = (sorted.length - 1) * q;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  if (low === high) return sorted[low];
  const weight = position - low;
  return sorted[low] * (1 - weight) + sorted[high] * weight;
}

export function summarize(values: readonly number[]): Distribution {
  if (values.length === 0) {
    return { count: 0, min: 0, max: 0, mean: 0, p50: 0, p95: 0, p99: 0 };
  }
  const sorted = [...values].sort((a, b) => a - b);
  let sum = 0;
  for (const value of sorted) sum += value;
  return {
    count: sorted.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    mean: sum / sorted.length,
    p50: quantileSorted(sorted, 0.50),
    p95: quantileSorted(sorted, 0.95),
    p99: quantileSorted(sorted, 0.99)
  };
}

export function estimateRefreshHz(frameMs: readonly number[]): number | null {
  const valid = frameMs.filter(value => Number.isFinite(value) && value > 1 && value < 100);
  if (valid.length < 30) return null;
  const median = summarize(valid).p50;
  return Math.round(1000 / median);
}
