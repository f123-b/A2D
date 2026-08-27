# P3-R7 Real Single-image E2E Contract v0.1

## Goal

Freeze the final Phase-3 acceptance path from one encoded character image through production decomposition and Phase-2 compilation into a Runtime-loadable `.a2d` package.

P3-R7 does **not** claim that a no-GPU CI runner executed See-through weights. It separates deterministic engineering validation from production-model validation.

## Gates

### Reference gate

Used by CI as a correctness oracle:

```text
single RGBA source
  ↓
ScriptedReferenceBackend
  ↓
P3 normalize/refine/complete/fuse
  ↓
P2 compile_avatar()
  ↓
Quality PASS
  ↓
character.a2d
  ↓
TypeScript loadA2DFromZip()
  ↓
E2E PASS
```

The scripted backend is explicitly non-production. Its purpose is to prove the cross-language package contract and orchestration path.

### Production gate

Production mode requires:

1. the production `SeeThroughProcessBackend` identity (`backend.name == see-through`);
2. P3 decomposition result ready;
3. P2 compiler present and `qa.ready == true`;
4. P3-R6 quality decision `PASS` / `readyForExport == true`;
5. non-empty `.a2d` with verified SHA-256;
6. TypeScript Runtime `loadA2DFromZip()` smoke pass.

If the Runtime smoke has not been executed, the final gate is `NOT_RUN`, never an implied pass.

## Bundle

The Python stage writes:

```text
<output>/
├── character.a2d                 # when P2 emitted an artifact
├── compiler-qa.json              # when compiler QA exists
├── quality-report.json           # when quality scoring exists
└── e2e-preflight.json
```

The Runtime stage writes:

```text
runtime-smoke.json
```

Finalization writes:

```text
e2e-report.json
```

## Production CLI

```bash
a2d-single-image-e2e run \
  --input character.png \
  --output ./out/e2e \
  --character-id character-001 \
  --see-through-root /opt/see-through \
  --completion-provider-factory mypkg.providers:make_completion \
  --landmark-provider-factory mypkg.providers:make_landmarks
```

Provider factories are optional zero-argument `module:attribute` callables. Missing providers are permitted to run, but P3-R6 may return `RETRY` or `MANUAL_REVIEW`, preventing the final production gate from passing.

After the Runtime smoke:

```bash
a2d-single-image-e2e finalize --output ./out/e2e
```

Exit codes:

```text
0 = final gate PASS
3 = runtime smoke NOT_RUN
4 = final gate FAIL
1 = command/configuration error
```

## Runtime smoke

The canonical Runtime acceptance loader is:

```text
@a2d/runtime-api/loadA2DFromZip
```

The smoke records:

- loader identity;
- part count;
- parameter count;
- buffer count;
- texture count;
- load error when rejected.

A package that exists as ZIP bytes but fails Runtime structural validation is an E2E failure.

## Evidence semantics

`mode=production` means the P3 production command path was requested and the backend identity is See-through. The report does not fabricate GPU hardware telemetry. Hardware/model execution evidence should be attached by the production environment or Studio telemetry in a later release process.

## Non-goals

- learned visual/aesthetic scoring;
- screenshot parity automation on headless CI;
- claiming See-through CUDA inference ran on GitHub-hosted CI;
- merging the stacked Phase-3 PRs.
