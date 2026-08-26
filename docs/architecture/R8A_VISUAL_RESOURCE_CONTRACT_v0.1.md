# R8A Visual Resource Contract v0.1

Status: **FROZEN FOR R8A BACKEND IMPLEMENTATION**

## Scope
R8A-1 freezes the data/compositing contract before WebGPU and WebGL2 visual rendering is implemented.

## Texture resources
`AvatarModelV1.textures[]` owns package texture assets.

Supported v1 formats:
- `rgba8` — deterministic raw RGBA test/embedded data
- `png`
- `webp`

Each resource declares `id`, package-relative `uri`, `byteLength`, format, alpha mode and filtering.
Raw RGBA8 also requires width/height and exact `width * height * 4` bytes.

Package paths must be relative and may not traverse with `..`.

## Atlas model
A texture resource may represent an entire atlas. Mesh UVs already point into atlas-normalized coordinates; parts do not own a separate pixel rectangle at runtime.

`Part.material.textureId` selects the atlas/resource. Legacy `textureAtlas` remains readable but is deprecated and is not the canonical R8A binding.

## Alpha contract
GPU shaders consume **premultiplied alpha**.

Encoded PNG/WebP is decoded with premultiplication. Raw RGBA8 marked `straight` is converted exactly once before upload.

Normal source-over is:

```text
out.rgb = src.rgb + dst.rgb * (1 - src.a)
out.a   = src.a   + dst.a   * (1 - src.a)
```

Material opacity multiplies premultiplied RGB and alpha together.

## Clipping contract
`Part.clip` references one or more source part IDs and uses:
- `inside`
- `outside`

Multiple source alpha masks combine as alpha union:

```text
coverage = 1 - product(1 - sourceAlpha[i])
inside   = coverage
outside  = 1 - coverage
```

This retains soft anti-aliased edges and avoids binary stencil semantics as the canonical model.
Backends may use any implementation that matches the reference coverage.

Invalid:
- empty source list
- unknown source part
- self-reference

## Immutable visual plan
At load time the runtime compiles:
- stable draw order
- material binding
- opacity
- canonical clip key
- source part indices

No material/mask graph rebuilding or draw-order sorting is allowed per frame.

## Backward compatibility
Models without `textures`, `material`, or `clip` remain valid. Existing R5/R6 synthetic and golden models therefore continue loading.

## Next gate: R8A-2
- WebGPU sRGB texture upload + sampler
- WebGL2 sRGB/linear texture upload + sampler
- premultiplied blend state
- soft mask render targets
- identical visual plan consumption
- visual golden images / pixel tolerance
