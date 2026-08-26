import type { Parameter } from "@a2d/avatar-schema";

export class ParameterCore {
  readonly definitions: readonly Parameter[];
  readonly values: Float32Array;
  readonly defaults: Float32Array;
  readonly indexById: ReadonlyMap<string, number>;

  private dirtyMin = Number.POSITIVE_INFINITY;
  private dirtyMax = -1;

  constructor(definitions: readonly Parameter[]) {
    this.definitions = definitions;
    this.values = new Float32Array(definitions.length);
    this.defaults = new Float32Array(definitions.length);

    const map = new Map<string, number>();
    definitions.forEach((p, i) => {
      if (map.has(p.id)) throw new Error(`duplicate parameter id: ${p.id}`);
      map.set(p.id, i);
      this.values[i] = p.default;
      this.defaults[i] = p.default;
    });
    this.indexById = map;
  }

  get length(): number {
    return this.values.length;
  }

  getIndex(id: string): number {
    const index = this.indexById.get(id);
    if (index === undefined) throw new Error(`unknown parameter: ${id}`);
    return index;
  }

  get(idOrIndex: string | number): number {
    const index = typeof idOrIndex === "string" ? this.getIndex(idOrIndex) : idOrIndex;
    this.assertIndex(index);
    return this.values[index];
  }

  set(idOrIndex: string | number, value: number): boolean {
    const index = typeof idOrIndex === "string" ? this.getIndex(idOrIndex) : idOrIndex;
    this.assertIndex(index);
    const def = this.definitions[index];
    const clamped = Math.min(def.max, Math.max(def.min, value));

    if (Object.is(this.values[index], clamped)) return false;
    this.values[index] = clamped;
    this.markDirty(index);
    return true;
  }

  setMany(values: Float32Array): void {
    if (values.length !== this.values.length) {
      throw new Error(`parameter count mismatch: expected ${this.values.length}, got ${values.length}`);
    }

    for (let i = 0; i < values.length; i++) this.set(i, values[i]);
  }

  reset(): void {
    for (let i = 0; i < this.values.length; i++) {
      if (!Object.is(this.values[i], this.defaults[i])) {
        this.values[i] = this.defaults[i];
        this.markDirty(i);
      }
    }
  }

  consumeDirtyRange(): { start: number; endExclusive: number } | null {
    if (this.dirtyMax < 0) return null;
    const range = { start: this.dirtyMin, endExclusive: this.dirtyMax + 1 };
    this.dirtyMin = Number.POSITIVE_INFINITY;
    this.dirtyMax = -1;
    return range;
  }

  private markDirty(index: number): void {
    this.dirtyMin = Math.min(this.dirtyMin, index);
    this.dirtyMax = Math.max(this.dirtyMax, index);
  }

  private assertIndex(index: number): void {
    if (!Number.isInteger(index) || index < 0 || index >= this.values.length) {
      throw new RangeError(`parameter index out of range: ${index}`);
    }
  }
}
