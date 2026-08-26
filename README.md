# A2D Studio

A2D Studio 是一个 **AI 驱动的 2D Avatar / Live2D 类角色生成与运行平台**。

目标流程：

```text
PNG / JPG / PSD
      ↓
AI Layer Decomposition
      ↓
Semantic Layer Normalization
      ↓
Auto Rig Compiler
      ↓
A2D Avatar IR (.a2d)
      ↓
GPU Runtime / Editor / Exporters
```

产品原则：

1. **操作最简单**：普通用户默认只需要“上传 → 自动生成 → 预览 → 使用”。
2. **运行性能优先**：Runtime 采用 GPU-first deformation；CPU/WASM 只负责 tracking、parameter、physics 和状态管理。
3. **自有 Avatar IR**：`.a2d` 是一级公民格式，Cubism / nijilive 兼容作为外部 exporter，不侵入核心数据模型。
4. **单一运行时语义**：Editor、Runtime、Exporter 共用同一个 Avatar IR 与形变定义，禁止复制两套形变算法。
5. **可测试、可量化**：性能使用 p50 / p95 / p99、CPU/GPU 时间、draw calls 和 golden vectors 验收。

## 当前状态

Phase 1 Runtime 已完成到 **R5 Physics v1**：

- [x] R1 `.a2d` Package Loader
- [x] R2 Parameter Core
- [x] R3 WebGL2 Reference Renderer
- [x] R4 GPU Morph / Pseudo3D Head
- [x] R5 Deterministic Spring Physics
- [ ] R6 WebGPU Renderer
- [ ] R7 Benchmark Suite
- [ ] R8 Full Golden Avatar

当前链路：

```text
Tracking / UI
      ↓
ParameterCore
      ↓
FixedStep Physics @ 120 Hz
      ↓
Dirty Parameter Upload
      ↓
GPU Morph / Deformer
      ↓
WebGL2 Render
```

## Monorepo

```text
apps/
  studio-web/          Web 编辑器 / Runtime Demo
packages/
  avatar-schema/       Avatar IR TypeScript 类型
  runtime-api/         Loader / Parameter / Deformer / Physics / Renderer
  tracking-api/        Tracking Adapter Contract
services/
  decomposer/          AI 拆层适配边界
  rig-compiler/        自动 Rig Compiler
crates/
  geometry/            后续 Rust/WASM geometry
  physics/             后续 Rust/WASM physics
  runtime-core/        后续 Rust/WASM runtime core
tools/
  benchmark/           Runtime / Physics benchmark
spec/                  .a2d / Avatar IR 规范与 Golden Models
docs/                  ADR / Architecture / Validation / Roadmap
```

## 关键规范

- `docs/architecture/ARCHITECTURE_FREEZE_v0.1.md`
- `docs/architecture/R4_GPU_DEFORMATION_CONTRACT_v0.1.md`
- `docs/architecture/R5_PHYSICS_CONTRACT_v0.1.md`
- `spec/a2d-container-v1.md`
- `spec/avatar-ir.schema.json`

## Golden Models

- `spec/examples/minimal-golden.a2d`
- `spec/examples/r4-golden.a2d`
- `spec/examples/r5-golden.a2d`

## Development

要求：

- Node.js 22+
- pnpm 10+
- Rust stable（Rust/WASM crates 开始实现后需要）

```bash
corepack enable
pnpm install
pnpm typecheck
pnpm test
pnpm build
```

运行 Web Runtime Demo：

```bash
pnpm --filter @a2d/studio-web dev
```

## Git Workflow

- `main`：稳定主线，只接受 PR 合并。
- `feat/<topic>`：功能开发。
- `fix/<topic>`：缺陷修复。
- `perf/<topic>`：性能优化。
- `docs/<topic>`：文档。
- `chore/<topic>`：工程维护。

Commit 使用 Conventional Commits，例如：

```text
feat(runtime): add WebGPU deformation backend
perf(renderer): batch parameter buffer uploads
fix(physics): clamp invalid spring state
```

详细规则见 `docs/GIT_WORKFLOW.md`。

## License

项目自有代码采用 Apache-2.0。第三方组件必须保留各自许可证和 NOTICE。
