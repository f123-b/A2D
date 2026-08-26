import fs from "node:fs";

function read(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function flatten(report) {
  if (report.result) return [report.result];
  if (Array.isArray(report.results)) return report.results.map(entry => entry.result ?? entry);
  throw new Error("unsupported R7 report format");
}

function key(result) {
  return `${result.backend}:${result.case.id}`;
}

function number(value, label) {
  if (!Number.isFinite(value)) throw new Error(`${label} is not finite`);
  return value;
}

const [, , baselinePath, candidatePath, ...flags] = process.argv;
if (!baselinePath || !candidatePath) {
  console.error("Usage: pnpm --filter @a2d/benchmark compare baseline.json candidate.json [--max-regression=0.08]");
  process.exit(2);
}

const maxRegressionFlag = flags.find(value => value.startsWith("--max-regression="));
const maxRegression = maxRegressionFlag ? Number(maxRegressionFlag.split("=")[1]) : 0.08;
if (!(maxRegression >= 0)) throw new Error("max regression must be >= 0");

const baseline = new Map(flatten(read(baselinePath)).map(result => [key(result), result]));
const candidate = flatten(read(candidatePath));
const rows = [];
let failed = false;

for (const result of candidate) {
  const previous = baseline.get(key(result));
  if (!previous) {
    rows.push({ case: key(result), status: "new" });
    continue;
  }

  const metrics = [
    ["frame.p95", previous.frameMs.p95, result.frameMs.p95],
    ["submit.p95", previous.submitCpuMs.p95, result.submitCpuMs.p95],
    ["physics.p95", previous.physicsMs.p95, result.physicsMs.p95]
  ];

  for (const [metric, beforeRaw, afterRaw] of metrics) {
    const before = number(beforeRaw, `${metric} baseline`);
    const after = number(afterRaw, `${metric} candidate`);
    const ratio = before > 0 ? (after - before) / before : 0;
    const status = ratio > maxRegression ? "regression" : "ok";
    if (status === "regression") failed = true;
    rows.push({ case: key(result), metric, before, after, regressionPercent: ratio * 100, status });
  }
}

console.table(rows);
if (failed) process.exit(1);
