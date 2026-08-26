# R8A-3 Visual Golden and Profiling Contract

Status: **IMPLEMENTED / HARDWARE DATA PENDING**

## Goals

R8A-3 adds two complementary validation layers:

1. a small deterministic visual `.a2d` model for semantic correctness
2. scalable synthetic visual workloads for runtime profiling

## Visual Golden Avatar

`spec/examples/r8a-visual-golden.a2d` contains:

- hair back
- body
- face
- left/right eye white
- left/right iris
- mouth
- front hair
- one PNG atlas
- two independent iris-inside-eye clip groups
- pseudo3d head XYZ
- one physics-driven `ParamHairX` morph

The artifact SHA-256 is pinned by `r8a-visual-golden-metadata.json` and checked in CI.

This is a functional visual golden, not final production artwork.

## Visual benchmark matrix

The core R7 cases remain unchanged. R8A-3 appends:

| Case | Vertices | Parts | Texture | Masks | Overdraw scale |
|---|---:|---:|---:|---:|---:|
| visual-textured-25k | 25k | 50 | 512² | 0 | 1.0 |
| visual-textured-50k | 50k | 100 | 512² | 0 | 1.0 |
| visual-masks-4 | 25k | 50 | 512² | 4 | 1.0 |
| visual-masks-16 | 25k | 50 | 512² | 16 | 1.0 |
| visual-masks-32 | 50k | 100 | 1024² | 32 | 1.0 |
| visual-overdraw-heavy | 50k | 100 | 1024² | 16 | 0.25 |

All visual synthetic parts share one atlas because A2D expects atlas-oriented content rather than one texture per layer.

## Visual metrics

Benchmark results now include:

- texture count
- texture asset bytes
- estimated decoded GPU texture bytes
- mask pass count
- mask source draw count
- main draw count
- estimated full-frame mask-target bytes

GPU timing already supplied by R7.1 measures mask + main visual work together.

## Intentional stress signal

The current v1 mask implementation uses one full-frame RGBA8 target per unique clip key.

At 1920x1080:

```text
1 mask  ~= 7.91 MiB
16 masks ~= 126.6 MiB
32 masks ~= 253.1 MiB
```

The 16/32-mask cases intentionally expose when this simple architecture should be replaced by mask atlasing/scissored targets.

## Hardware gate

The current CI validates generation, structure and golden artifact integrity. It does not claim real GPU performance or screenshot parity.

Hardware validation must run WebGPU and WebGL2 on the same machine/browser family and save JSON reports for at least:

- visual-textured-25k
- visual-masks-16
- visual-overdraw-heavy
- the R8A visual golden model
