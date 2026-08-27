# P3-R3 Semantic Refinement Contract v0.1

## Goal

Convert normalized production-model observations into the canonical A2D semantic set without hiding uncertainty or inventing unsupported pixels.

## Input / output

```text
DecomposerResultV1
+ SourceImageRgba
        ↓
refine_decomposer_result()
        ↓
DecomposerResultV1
```

The output remains the P3-R1 contract; Phase 2 does not gain a new ABI.

## Required semantic gate

The release-facing required set is:

```text
body
face
eye_white_l
eye_white_r
iris_l
iris_r
mouth
```

P3-R3 may repair a missing item only when a deterministic source rule exists. Anything still missing produces an `error / required-semantic-missing` finding.

## Body proxy

When `body` is absent and `cloth` exists, P3-R3 creates a body proxy from the real cloth RGBA/matte:

- identical bbox/raster/mask
- `z_order = cloth.z_order - 1`
- confidence multiplied by `body_proxy_confidence_scale`
- explicit `body-proxy-synthesized` warning

This is a rigging proxy, not anatomy completion. P3-R4 may later replace it with a completed body.

## Pair repair

Pairs:

```text
eye_white_l / eye_white_r
iris_l      / iris_r
brow_l      / brow_r
```

If exactly one side exists and `face` exists:

- mirror bbox about face center
- horizontally mirror RGBA/A8
- confidence is multiplied by `mirror_confidence_scale`
- emit `semantic-pair-mirrored`

If both sides exist, P3-R3 checks gross bbox and confidence symmetry and emits non-blocking mismatch warnings.

## Side-hair extraction

`hair_side_l/r` may be derived from existing `hair_front` or `hair_back` only.

Pixels must:
- have non-zero source alpha
- lie outside the configurable face-core x range
- lie below the configured upper-face threshold
- satisfy a minimum active-pixel count

Generated side hair keeps the real source pixels and receives `side_hair_confidence_scale`.

## Visual-order repair

The following relations are enforced deterministically:

```text
hair_back < body < cloth
body < face
face < eye_white / mouth / brow / hair_front
eye_white < iris
```

Corrections emit `semantic-z-order-corrected`.

## Parent hints

Canonical parent hints are emitted only when the target parent exists:

```text
cloth       → body
face        → body
eye white   → face
iris        → eye white
brow/mouth  → face
hair front/side → face
hair back   → body
```

## Confidence

Synthetic/refined observations never increase confidence above their source. Default penalties:

```text
mirror      0.72
body proxy  0.62
side hair   0.78
```

## Determinism

Output must be stable for equivalent layer ordering. The refined `sourceRevision` hashes the previous revision, full refinement config, and contract version.

## Non-goals

P3-R3 does not:
- inpaint occluded pixels
- infer landmarks
- synthesize missing eyes when neither side exists
- turn arbitrary clothing into anatomy
- invent hair where no real hair pixels exist
