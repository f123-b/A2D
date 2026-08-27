# P3-R1 Decomposer Contract v0.1

## Goal

Freeze the model-independent boundary between a flat source image and the Phase-2 normalized semantic-layer package.

## Source contract

`SourceImageRgba` is decoded, straight-alpha RGBA8:

- width/height are positive integers
- byte length is exactly `width * height * 4`
- source coordinates use top-left origin, +x right, +y down

Image decoding is outside P3-R1. P3-R2 may use Pillow/OpenCV/browser/native decoders without changing this contract.

## Backend protocol

A `DecompositionBackend` receives the source image and returns `BackendDecompositionV1`:

```text
layers[]
  source_key
  semantic_label
  pixel bbox
  cropped RGBA8
  cropped A8 mask
  z_order
  confidence
  optional parent_source_key

landmarks[]
  label
  x/y in source pixels
  confidence

backend_name
backend_revision
```

Backend labels are not part of the A2D public vocabulary. They are normalized by the adapter boundary.

## Semantic normalization

Output semantic vocabulary is exactly the existing normalized-layer contract:

`body cloth face brow_l brow_r eye_white_l eye_white_r iris_l iris_r mouth hair_front hair_side_l hair_side_r hair_back accessory`

Canonical non-accessory semantics must be unique. P3-R1 rejects ambiguous duplicate outputs instead of picking a winner silently. Accessories are intentionally multi-instance and receive deterministic `accessory-001`, `accessory-002`, ... IDs.

## Mask and image materialization

The backend observation bbox is only a search/crop window. P3-R1 computes the tight active-alpha rectangle using `alpha_threshold` and emits the smaller final asset.

For every retained pixel:

```text
out.rgb = source crop rgb
out.a   = round(source.a * mask.a / 255)
```

The corresponding A8 mask is stored independently for P2 mesh generation.

Assets:

```text
layers/<layer-id>.rgba
masks/<layer-id>.a8
```

## Coordinates

Final bbox and landmarks are normalized against the original source canvas, never against the crop:

```text
x_norm = x_pixel / canvas_width
y_norm = y_pixel / canvas_height
```

This makes P3 output resolution-independent and directly compatible with P2-R1.

## Parent graph

`parent_source_key` is resolved only after semantic filtering/stable-ID assignment.

Hard errors:

- missing retained parent
- self-parent
- parent cycle

## Findings policy

P3-R1 findings are deterministic and explicit.

Blocking:

- empty active mask
- malformed source/observation buffers
- duplicate canonical non-accessory semantic
- duplicate canonical landmark
- invalid parent graph

Non-blocking warnings:

- layer confidence below configured threshold
- landmark confidence below configured threshold

Informational:

- unsupported semantic label
- unsupported landmark label

P3-R1 does not duplicate P2 required-semantic policy. If face/mouth/eyes are absent, P2-R1 remains the authoritative compile blocker.

## Determinism

For equal source bytes, backend identity/revision and logically equal observations, normalized output must not depend on Python mapping/tuple order.

Stable ordering:

- layers: `(z_order, output_id)`
- landmarks: canonical ID
- assets: layer ID
- findings: severity/code/subject/message

`sourceRevision` is SHA-256 over source dimensions, source RGBA bytes, backend name and backend revision.

## AI integration rule

See-through/SAM/face-landmark model code must remain behind `DecompositionBackend`. P2 compiler and A2D Runtime must never depend on upstream model class names, label names, tensor shapes, checkpoint paths, or framework-specific objects.
