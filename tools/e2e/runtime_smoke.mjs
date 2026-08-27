import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import { loadA2DFromZip } from "../../packages/runtime-api/dist/packageLoader.js";
import { zipReaderFromArrayBuffer } from "../../packages/runtime-api/dist/jsZipReader.js";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  console.error("usage: node tools/e2e/runtime_smoke.mjs <character.a2d> <runtime-smoke.json>");
  process.exit(2);
}

let summary;
try {
  const bytes = fs.readFileSync(inputPath);
  const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const reader = await zipReaderFromArrayBuffer(arrayBuffer);
  const loaded = await loadA2DFromZip(reader);
  summary = {
    passed: true,
    loader: "@a2d/runtime-api/loadA2DFromZip",
    partCount: loaded.model.parts.length,
    parameterCount: loaded.model.parameters.length,
    bufferCount: loaded.buffers.size,
    textureCount: loaded.model.textures?.length ?? 0
  };
} catch (error) {
  summary = {
    passed: false,
    loader: "@a2d/runtime-api/loadA2DFromZip",
    partCount: 0,
    parameterCount: 0,
    bufferCount: 0,
    textureCount: 0,
    error: error instanceof Error ? `${error.name}: ${error.message}` : String(error)
  };
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
if (!summary.passed) process.exit(1);
