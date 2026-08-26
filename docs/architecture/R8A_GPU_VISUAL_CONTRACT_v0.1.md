# R8A GPU Visual Runtime Contract v0.1

Status: **IMPLEMENTED / HARDWARE VISUAL VALIDATION PENDING**

## Purpose

R8A-2 connects the R8A-1 visual resource contract to both GPU backends without changing Avatar IR semantics.

## Rendering order

Per frame:

```text
parameter / physics update
  -> GPU deformation state
  -> soft mask passes (one per unique clip key)
  -> main premultiplied-alpha pass
```

## Textures

- Runtime decodes all declared texture resources once during renderer creation.
- `rgba8` data is already premultiplied before GPU upload.
- PNG/WebP uses the browser image decoder with premultiplied alpha enabled.
- Missing material texture uses an opaque 1x1 white fallback so legacy models remain visible.

## Main blending

Both WebGPU and WebGL2 use premultiplied source-over:

```text
src = ONE
dst = ONE_MINUS_SRC_ALPHA
```

for color and alpha.

## Soft masks

Each unique `clip.key` owns a full-frame RGBA8 mask render target.

Mask source parts are rendered into the target with the same premultiplied source-over blend. The resulting alpha therefore implements:

```text
coverage = 1 - Π(1 - sourceAlpha)
```

The main fragment samples mask coverage in framebuffer space.

- inside: multiply by coverage
- outside: multiply by `1 - coverage`

Mask-source parts are rendered from their direct material alpha in v1; recursive clipping of mask sources is intentionally not evaluated.

## Performance constraints

- textures are decoded/uploaded once
- visual draw plan is immutable after load
- mesh topology remains GPU resident
- mask targets are recreated only on framebuffer resize
- no GPU/CPU readback is required for clipping
- GPU timing includes mask passes and the main pass

## Backward compatibility

Models without `textures`, `material` or `clip` continue to render through the opaque-white fallback texture.

## Validation

CI validates TypeScript/build/tests and CPU visual golden math.

Hardware-complete validation still requires:
- real WebGPU texture sampling
- real WebGL2 texture sampling
- premultiplied edge inspection
- eye-white -> iris inside clipping
- outside clipping
- WebGPU/WebGL2 screenshot parity
