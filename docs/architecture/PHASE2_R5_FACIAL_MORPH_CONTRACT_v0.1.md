# Phase 2 R5 — Facial Morph Compiler Contract v0.1

## Goal

Compile topology-independent `MorphIntent` rules plus an actual `AdaptiveMesh` into the exact morph data already consumed by the Phase-1 Runtime.

```text
MorphIntent
    +
AdaptiveMesh
    +
Semantic Rig Pivot
    +
R8B parameter table
      ↓
per-vertex delta + falloff
      ↓
contiguous vertex influence ranges
      ↓
Runtime ABI
```

## Runtime ABI

Each packed influence is exactly 16 bytes, little-endian:

```text
u32 parameterIndex
f32 deltaX
f32 deltaY
f32 weight
```

Each vertex owns one contiguous range:

```text
u32 start
u32 count
```

The current Runtime v1 limit is **8 influences per vertex**. The compiler rejects plans that exceed it rather than truncating data.

## Determinism

For identical semantic input, mesh and parameter table:

- intent input order must not affect output;
- records are ordered by vertex, then parameter index, then intent id;
- every vertex receives exactly one range, including zero-count ranges;
- all ranges are contiguous and cover all records exactly once.

## Parameter ABI

`parameterIndex` is the index in `RigPlanV1.parameter_ids`.

The compiler never invents, reorders or silently substitutes parameter ids. Unknown parameter references are hard errors.

## Morph operations v0.1

### Eye close

`eye_close_y`

- eye corners receive a smooth pinned falloff;
- upper/lower vertices carry opposite signed Y deltas;
- the Runtime's normalized negative value for closing moves both sides toward the eye pivot.

### Mouth open

`mouth_open_y`

- upper vertices move upward;
- lower vertices move downward;
- center vertices have stronger weight than mouth corners.

### Mouth form

`mouth_form_x`

- corners move horizontally away from/toward the mouth pivot;
- positive form adds a small upward corner lift;
- negative parameter input reverses the linear field.

v0.1 uses the Runtime's current single linear influence field. Truly asymmetric negative/positive mouth keyforms require a future multi-key morph extension.

### Brow Y

`brow_translate_y`

Positive input moves the brow upward in canvas coordinates.

### Brow angle

`brow_rotate`

Compiles the semantic brow pivot and configured angle into per-vertex rotation deltas.

### Body breath

`body_breath_scale_y`

Scales vertices vertically away from the body/neck pivot.

## Validation

The compiler rejects:

- duplicate parameter ids;
- unknown parameter references;
- unsupported operations;
- non-finite mesh positions;
- non-finite/negative amplitudes;
- malformed or unsorted key values;
- non-contiguous range layouts;
- invalid weights;
- more than 8 influences on one vertex.

## Packing

`pack_morph_influences()` emits the 16-byte Runtime record array.

`pack_morph_ranges()` emits the 8-byte-per-vertex `uvec2(start,count)` array.

`pack_morph_buffers()` returns both.
