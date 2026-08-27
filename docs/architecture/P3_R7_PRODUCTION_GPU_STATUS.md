# P3-R7 Production GPU Validation Status

Status: **EXECUTION STARTED / SELF-HOSTED GPU RUNNER REQUIRED**

This document tracks the final production-only gate after the repository reference E2E passed.

## What is already proven

- P3-R1..R7 repository contracts are implemented.
- P2 one-click compilation produces `.a2d`.
- the reference single-image pipeline reaches P3-R6 quality PASS.
- the generated `.a2d` is accepted by TypeScript `loadA2DFromZip()`.
- CI #40 completed successfully for PR #21.

## What this branch adds

- `.github/workflows/production-gpu-e2e.yml`
- `tools/e2e/production_gpu_preflight.py`
- `docs/architecture/PRODUCTION_GPU_E2E_RUNBOOK.md`

The production workflow is automatically attempted on pushes to `feat/production-gpu-validation` and can also be started manually with `workflow_dispatch`.

## Required execution environment

The workflow targets the standard self-hosted labels:

```text
[self-hosted, linux, x64]
```

The preflight itself verifies that the machine actually has NVIDIA/CUDA support and enough VRAM.

Required repository variables:

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

## Production PASS is not declared until

```text
real image
  → pinned See-through / CUDA
  → production completion provider
  → production landmark provider
  → P2 QA ready
  → P3-R6 quality PASS
  → character.a2d
  → TypeScript Runtime loader PASS
  → e2e-report.json mode=production gate=pass
```

A queued self-hosted job is an infrastructure blocker, not a pipeline failure. A preflight failure is an environment/provider/model failure and must not be bypassed by lowering quality thresholds.
