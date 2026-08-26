import JSZip from "jszip";
import type { ZipReader } from "./packageLoader.js";

export async function zipReaderFromArrayBuffer(bytes: ArrayBuffer): Promise<ZipReader> {
  const zip = await JSZip.loadAsync(bytes);
  return {
    has(path: string): boolean {
      return zip.file(path) !== null;
    },
    async readText(path: string): Promise<string> {
      const f = zip.file(path);
      if (!f) throw new Error(`ZIP entry missing: ${path}`);
      return f.async("text");
    },
    async readArrayBuffer(path: string): Promise<ArrayBuffer> {
      const f = zip.file(path);
      if (!f) throw new Error(`ZIP entry missing: ${path}`);
      return f.async("arraybuffer");
    }
  };
}
