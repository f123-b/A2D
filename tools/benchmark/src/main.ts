import { BENCHMARK_MATRIX } from "./contract.js";
import { evaluate } from "./evaluator.js";
import { runBenchmarkCase, type BenchmarkResult } from "./runner.js";

const canvas = document.querySelector<HTMLCanvasElement>("#stage")!;
const backend = document.querySelector<HTMLSelectElement>("#backend")!;
const caseSelect = document.querySelector<HTMLSelectElement>("#case")!;
const runButton = document.querySelector<HTMLButtonElement>("#run")!;
const matrixButton = document.querySelector<HTMLButtonElement>("#matrix")!;
const copyButton = document.querySelector<HTMLButtonElement>("#copy")!;
const downloadButton = document.querySelector<HTMLButtonElement>("#download")!;
const status = document.querySelector<HTMLPreElement>("#status")!;

let latest: unknown = null;

for (const item of BENCHMARK_MATRIX) {
  const option = document.createElement("option");
  option.value = item.id;
  option.textContent = `${item.id}: ${item.vertices}v / ${item.parts}p / ${item.parameters}param / ${item.physicsChains}phys`;
  caseSelect.append(option);
}

function selectedBackend(): "webgpu" | "webgl2" {
  return backend.value === "webgl2" ? "webgl2" : "webgpu";
}

function setBusy(busy: boolean): void {
  runButton.disabled = busy;
  matrixButton.disabled = busy;
  backend.disabled = busy;
  caseSelect.disabled = busy;
}

function publish(value: unknown): void {
  latest = value;
  copyButton.disabled = false;
  downloadButton.disabled = false;
  status.textContent = JSON.stringify(value, null, 2);
}

runButton.addEventListener("click", async () => {
  const item = BENCHMARK_MATRIX.find(value => value.id === caseSelect.value)!;
  setBusy(true);
  try {
    const result = await runBenchmarkCase(canvas, item, selectedBackend(), message => {
      status.textContent = message;
    });
    publish({ result, gate: evaluate(result) });
  } catch (error) {
    status.textContent = error instanceof Error ? error.stack ?? error.message : String(error);
  } finally {
    setBusy(false);
  }
});

matrixButton.addEventListener("click", async () => {
  setBusy(true);
  const results: Array<{ result: BenchmarkResult; gate: ReturnType<typeof evaluate> }> = [];
  try {
    for (let index = 0; index < BENCHMARK_MATRIX.length; index++) {
      const item = BENCHMARK_MATRIX[index];
      status.textContent = `[${index + 1}/${BENCHMARK_MATRIX.length}] ${item.id}`;
      const result = await runBenchmarkCase(canvas, item, selectedBackend(), message => {
        status.textContent = `[${index + 1}/${BENCHMARK_MATRIX.length}] ${message}`;
      });
      results.push({ result, gate: evaluate(result) });
    }
    publish({
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      backend: selectedBackend(),
      results
    });
  } catch (error) {
    status.textContent = error instanceof Error ? error.stack ?? error.message : String(error);
  } finally {
    setBusy(false);
  }
});

copyButton.addEventListener("click", async () => {
  if (latest === null) return;
  await navigator.clipboard.writeText(JSON.stringify(latest, null, 2));
});

downloadButton.addEventListener("click", () => {
  if (latest === null) return;
  const blob = new Blob([JSON.stringify(latest, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `a2d-r7-${selectedBackend()}-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});
