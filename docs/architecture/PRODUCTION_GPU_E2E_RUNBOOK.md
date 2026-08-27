# Production GPU E2E Runbook

This runbook is the external acceptance gate for P3-R7. It does **not** replace the repository reference E2E; it proves the real production model stack on a CUDA machine.

## Runner contract

The workflow targets GitHub's default self-hosted Linux x64 labels:

```text
self-hosted
linux
x64
```

GPU capability is not trusted from a label. The preflight requires a real NVIDIA device, `nvidia-smi`, `torch.cuda.is_available()`, and sufficient VRAM.

The runner must already have a Python environment that can execute the pinned See-through checkout. The default See-through pipeline needs roughly 12–16 GB VRAM at 1280; `A2D_GROUP_OFFLOAD=true` lowers the preflight floor to 10 GB.

## Required repository variables

```text
A2D_SEE_THROUGH_ROOT
A2D_COMPLETION_PROVIDER_FACTORY
A2D_LANDMARK_PROVIDER_FACTORY
```

Optional:

```text
A2D_GPU_PYTHON
A2D_E2E_IMAGE
A2D_GROUP_OFFLOAD
```

`A2D_GPU_PYTHON` defaults to `python`.

`A2D_E2E_IMAGE` defaults to:

```text
${A2D_SEE_THROUGH_ROOT}/assets/test_image.png
```

which is the official See-through single-image demo source. For release validation, point `A2D_E2E_IMAGE` to a retained real-character corpus image instead.

Provider variables use the same zero-argument factory syntax as the P3-R7 CLI:

```text
mypkg.providers:make_completion
mypkg.providers:make_landmarks
```

The factories must return providers with non-empty `provider_name` and `provider_revision`.

## Pinned See-through revision

The preflight requires:

```text
7f139bb25c46a0c8ac720d95ddab185fcda5451c
```

unless the preflight is invoked manually with `--allow-unpinned`. The GitHub production workflow intentionally does not use that override.

## What the workflow executes

```text
NVIDIA / CUDA / VRAM preflight
        ↓
provider import + identity validation
        ↓
P3-R2 SeeThroughProcessBackend
        ↓
P3-R3 semantic refinement
        ↓
P3-R4 production completion provider
        ↓
P3-R5 production landmark provider
        ↓
P2 one-click compiler
        ↓
P3-R6 quality score
        ↓
character.a2d
        ↓
TypeScript loadA2DFromZip()
        ↓
P3-R7 finalize
        ↓
mode=production + gate=pass
```

The final assertion requires all of:

- backend identity is `see-through`
- P3 ready
- P2 QA ready
- quality decision is `pass`
- `readyForExport=true`
- non-empty `.a2d` with verified SHA-256
- TypeScript Runtime loader passes
- final E2E gate is `pass`

## Evidence artifact

The workflow uploads `production-gpu-e2e` containing, when available:

```text
a2d-gpu-preflight.json
character.a2d
compiler-qa.json
quality-report.json
e2e-preflight.json
runtime-smoke.json
e2e-report.json
```

Retain `e2e-report.json` together with the source-image revision and provider/model revisions for release evidence.

## If the job stays queued

A queued `Production GPU E2E` job means GitHub cannot currently find an online self-hosted Linux x64 runner for the repository. That is an infrastructure blocker, not a model or compiler failure.

## If preflight fails

The JSON preflight reports each condition separately:

- `nvidia-smi-present`
- `nvidia-smi-query`
- `gpu-vram`
- `torch-cuda`
- `see-through-script`
- `source-image`
- `see-through-revision`
- `completion-provider`
- `landmark-provider`

Do not lower the final P3-R6 or P3-R7 gate just to turn the production run green. Fix the failing environment/model/provider condition instead.
