# Git Workflow

## Protected main

`main` 是唯一稳定主线。推荐 GitHub Branch Protection：

- Require pull request before merging
- Require at least 1 approval
- Require status checks: `TypeScript`, `Rust workspace`
- Require conversation resolution
- Block force pushes
- Block branch deletion

## Branch naming

```text
feat/webgpu-renderer
feat/auto-rig-mesh
fix/a2d-buffer-validation
perf/deformer-batching
refactor/runtime-core
chore/ci-cache
```

## Commit policy

一个 commit 只做一个逻辑修改，禁止把功能、格式化和无关重构混在一起。

```text
feat(runtime): add WebGPU storage buffers
feat(schema): add mask graph to Avatar IR
perf(renderer): batch draw records by atlas
fix(loader): reject overlapping invalid views
```

## Merge policy

默认使用 **Squash Merge**：

- PR 内允许多个迭代 commit。
- 合并到 `main` 时形成一个清晰的 Conventional Commit。
- Architecture Freeze / release checkpoint 可保留独立里程碑 commit。

## Tags

版本格式：

```text
v0.1.0
v0.2.0
v1.0.0
```

Phase checkpoint 可使用 annotated tag：

```text
phase1-r5
phase1-runtime-complete
```

## Architecture changes

以下修改必须新增 ADR：

- `.a2d` container breaking change
- Avatar IR breaking change
- parameter normalization change
- deformation order change
- physics solver semantics change
- backend-independent Runtime API breaking change
