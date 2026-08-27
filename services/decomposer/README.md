# A2D Decomposer

Phase 3 converts one flat source image into the normalized semantic-layer package consumed by the Phase-2 rig compiler, then evaluates whether the generated `.a2d` is safe for automatic export.

## Pipeline

```text
PNG / JPG / RGBA
        ↓
Production backend
        ↓
P3-R1 normalization
        ↓
P3-R3 semantic refinement
        ↓
P3-R4 occlusion completion
        ↓
P3-R5 landmark fusion
        ↓
P2 compile_avatar()
        ↓
P3-R6 quality scoring
        ↓
P3-R7 E2E package/runtime gate
        ↓
PASS / RETRY / MANUAL_REVIEW / BLOCK
```

## P3-R1 — model-independent normalization

`DecompositionBackend` isolates model code from downstream A2D stages. The dependency-free `ScriptedReferenceBackend` remains the correctness oracle.

Normalization guarantees canonical semantic aliases, active-alpha tight crops, normalized `[0,1]` geometry, deterministic assets, explicit confidence findings, parent-graph validation and source revision hashing.

## P3-R2 — production adapter

`SeeThroughProcessBackend` integrates the public See-through V3 command-line pipeline through `inference/scripts/inference_psd.py` and consumes non-PSD `optimized/info.json + <tag>.png` output. Model weights, PyTorch and CUDA remain outside A2D.

## P3-R3 — semantic refinement

`refine_decomposer_result()` converts production-model output toward the canonical Phase-2 semantic shape without silently hallucinating unsupported content. It supports conservative body proxy synthesis, one-sided eye/iris/brow mirroring, real-pixel side-hair extraction, pair checks, deterministic z-order repair and required-semantic gating.

## P3-R4 — occlusion completion

`CompletionProvider` is the model-independent inpainting boundary. Providers receive the source image, target layer, visible pixels and an explicit completion mask. Pixels outside that mask must remain byte-identical.

`DeterministicReferenceCompletionProvider` is a correctness oracle, not a production visual inpainting model.

## P3-R5 — landmark fusion

`LandmarkProvider` is the production landmark-model boundary. P3-R5 combines direct backend landmarks, provider candidates and deterministic semantic-layer geometry. High-confidence existing landmarks are preserved exactly; agreeing evidence is fused; disagreeing evidence keeps the strongest source with an explicit confidence penalty.

## P3-R6 — quality scoring

`score_character_quality()` emits `CharacterQualityReportV1` with six weighted dimensions:

```text
semantic     25
completion   20
landmark     20
consistency  10
synthetic    10
compiler     15
             ---
             100
```

Decision policy:

```text
P3/P2 hard error                    → BLOCK
retryable model/provider issue      → RETRY
manual semantic/landmark review     → MANUAL_REVIEW
score >= 85 with no review action   → PASS
70 <= score < 85                    → MANUAL_REVIEW
score < 70                          → RETRY
```

Only `PASS` sets `readyForExport=true`. Valid P2 artifacts are kept for Studio preview when the decision is `RETRY` or `MANUAL_REVIEW`.

## P3-R7 — single-image E2E acceptance

P3-R7 separates two kinds of evidence.

### Reference CI gate

GitHub Actions runs a real cross-language package path:

```text
single RGBA source
→ ScriptedReferenceBackend
→ full P3/P2 pipeline
→ Quality PASS
→ character.a2d
→ @a2d/runtime-api/loadA2DFromZip()
→ e2e-report.json gate=pass
```

The scripted backend is intentionally not production AI. This gate proves orchestration, package bytes and Runtime compatibility.

### Production gate

Use the CLI on a machine with See-through V3 and its weights:

```bash
a2d-single-image-e2e run \
  --input character.png \
  --output ./out/e2e \
  --character-id character-001 \
  --see-through-root /opt/see-through \
  --completion-provider-factory mypkg.providers:make_completion \
  --landmark-provider-factory mypkg.providers:make_landmarks
```

The command writes:

```text
character.a2d
compiler-qa.json
quality-report.json
e2e-preflight.json
```

Then run the canonical Runtime smoke and finalize:

```bash
node tools/e2e/runtime_smoke.mjs \
  ./out/e2e/character.a2d \
  ./out/e2e/runtime-smoke.json

PYTHONPATH=services/decomposer:services/rig-compiler \
python -m a2d_decomposer.e2e_cli finalize --output ./out/e2e
```

Production `PASS` requires:

```text
backend.name == see-through
P3 ready
P2 QA ready
Quality == PASS
artifact SHA valid
Runtime loadA2DFromZip == PASS
```

If the Runtime smoke was not executed, the gate is explicitly `NOT_RUN` rather than an implied success.

The report contract is frozen in `spec/single-image-e2e-report.schema.json`.

## Tests

```bash
PYTHONPATH=services/decomposer:services/rig-compiler \
python -m unittest discover -s services/decomposer/tests -v
```

## Phase 3 acceptance boundary

The repository now contains the full single-image orchestration and Runtime acceptance harness. A final production claim still requires executing the production command on a real character image with pinned See-through weights/CUDA and retaining the resulting `e2e-report.json` as evidence.
