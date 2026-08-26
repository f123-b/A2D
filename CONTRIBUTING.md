# Contributing

## Branches

不要直接在 `main` 开发。使用：

- `feat/*`
- `fix/*`
- `perf/*`
- `refactor/*`
- `docs/*`
- `chore/*`

## Commit format

使用 Conventional Commits：

```text
<type>(<scope>): <summary>
```

推荐 type：

- `feat`
- `fix`
- `perf`
- `refactor`
- `test`
- `docs`
- `chore`
- `ci`

## Pull request gate

PR 合并前至少满足：

1. TypeScript strict typecheck 通过。
2. Unit / golden tests 通过。
3. Runtime 数学变更必须更新 golden vectors。
4. Avatar IR 变更必须更新 schema + ADR / migration 说明。
5. Runtime 热路径变更必须说明性能影响。
6. 禁止把 Cubism / nijilive 私有字段变成核心 Avatar IR 必需字段。

## Performance-sensitive changes

Renderer / Physics / Deformer PR 应附：

- 测试模型规模
- p50 / p95 / p99 frame time
- CPU time
- GPU time（可获取时）
- draw calls
- 与基线的增减百分比
