# A2D Decomposer

Phase 3 converts one flat source image into the normalized semantic-layer package consumed by the Phase-2 rig compiler.

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
PASS / RETRY / MANUAL_REVIEW / BLOCK
        ↓
.a2d preview / auto export gate
```

## P3-R1 — model-independent normalization

The `DecompositionBackend` protocol isolates model code from downstream A2D stages. The zero-dependency `ScriptedReferenceBackend` remains the correctness oracle.

Normalization guarantees canonical semantic aliases, active-alpha tight crops, normalized `[0,1]` geometry, deterministic assets, explicit confidence findings, parent-graph validation and source revision hashing.

## P3-R2 — production adapter

`SeeThroughProcessBackend` integrates the public See-through V3 command-line pipeline through `inference/scripts/inference_psd.py` and consumes non-PSD `optimized/info.json + <tag>.png` output. Model weights, PyTorch and CUDA remain outside A2D.

## P3-R3 — semantic refinement

`refine_decomposer_result()` converts production-model output toward the canonical Phase-2 semantic shape without silently hallucinating unsupported content:

- body proxy only from a real cloth matte, with confidence penalty
- one missing eye/iris/brow side can be mirrored from the detected side
- side hair is extracted only from real front/back hair pixels
- pair geometry/confidence inconsistencies are reported
- core draw-order conflicts are corrected deterministically
- canonical parent hints are emitted
- missing required semantics remain blocking

## P3-R4 — occlusion completion

`CompletionProvider` is the model-independent inpainting boundary. Providers receive the source image, target layer, visible pixels and an explicit completion mask. Pixels outside that mask must remain byte-identical.

Current completion targets are face holes covered by front/side hair and body holes covered by cloth. The P3-R3 body proxy is explicitly marked for full local completion.

`DeterministicReferenceCompletionProvider` is a correctness oracle, not a production visual inpainting model.

## P3-R5 — landmark fusion

`LandmarkProvider` is the production landmark-model boundary. P3-R5 combines direct backend landmarks, provider candidates and deterministic semantic-layer geometry.

Canonical output includes head/nose/neck, eye/iris/mouth/brow centers and hair roots. High-confidence existing landmarks are preserved exactly, agreeing evidence is confidence-weighted, and disagreeing evidence selects the strongest source with an explicit confidence penalty.

## P3-R6 — quality scoring

`score_character_quality()` produces a stable `CharacterQualityReportV1` after P2 compilation.

The score is the weighted combination of six independent dimensions:

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

The default decision policy is:

```text
P3/P2 hard error                    → BLOCK
retryable model/provider issue      → RETRY
manual semantic/landmark review     → MANUAL_REVIEW
score >= 85 with no review action   → PASS
70 <= score < 85                    → MANUAL_REVIEW
score < 70                          → RETRY
```

`PASS` is the only decision with `readyForExport=true`. `RETRY` and `MANUAL_REVIEW` do **not** discard a valid P2 `.a2d`; the artifact remains available for Studio preview, inspection and repair.

Actions are machine-readable, for example:

```text
run_completion
run_landmark_provider
rerun_decomposition
review_semantics
review_landmarks
review_compiler
fix_compiler
```

The JSON contract is frozen in `spec/character-quality-report.schema.json`.

### One-click bridge

```python
result = decode_decompose_and_compile(
    "character-id",
    encoded_png_or_jpg,
    see_through_backend,
    completion_provider=my_inpainting_provider,
    landmark_provider=my_landmark_provider,
)

if result.quality and result.quality.ready_for_export:
    a2d_bytes = result.compiler.artifact.a2d
elif result.compiler and result.compiler.artifact:
    preview_bytes = result.compiler.artifact.a2d
```

The default ordering is:

```text
decompose
→ normalize
→ refine
→ complete
→ fuse landmarks
→ P2 compile
→ quality score
```

Debugging can independently disable refinement, completion, landmark fusion or quality scoring with:

```text
refine_semantics=False
complete_hidden=False
fuse_landmarks_enabled=False
quality_scoring_enabled=False
```

## Tests

```bash
PYTHONPATH=services/decomposer:services/rig-compiler \
python -m unittest discover -s services/decomposer/tests -v
```

## Next

P3-R7 Real Single-image E2E:
- real See-through V3 weights + CUDA
- production completion provider
- production landmark provider
- real character image corpus
- quality gate regression thresholds
- generated `.a2d` visual/runtime validation
