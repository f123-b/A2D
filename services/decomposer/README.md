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
P3→P2 bridge
        ↓
compile_avatar()
        ↓
.a2d
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

`LandmarkProvider` is the production landmark-model boundary. It emits normalized candidates with confidence; P3-R5 fuses those candidates with:

1. already-normalized backend landmarks;
2. deterministic geometry evidence from the semantic layers;
3. alpha-weighted centroids for facial parts;
4. alpha top-band centroids for hair roots.

Canonical output includes, when source semantics permit:

```text
head_center
nose
neck
eye_l_center / eye_r_center
iris_l_center / iris_r_center
mouth_center
brow_l_center / brow_r_center
hair_front_root
hair_side_l_root / hair_side_r_root
hair_back_root
```

Fusion policy:

- existing landmark confidence `>= 0.90`: preserve exact coordinates/confidence
- agreeing evidence: confidence-weighted position fusion
- conflicting evidence: select the strongest source, reduce confidence, emit `landmark-disagreement`
- geometry-only weak estimates remain explicitly low confidence
- provider exceptions/invalid duplicate canonical landmarks are blocking
- unsupported provider landmark labels are informational, not silently remapped

P3-R5 deliberately derives `nose` and `neck` conservatively when no model provides them. Geometry fallback is sufficient for P2 pivots/Proxy-Z but remains lower confidence for the later quality gate.

### One-click bridge

```python
result = decode_decompose_and_compile(
    "character-id",
    encoded_png_or_jpg,
    see_through_backend,
    completion_provider=my_inpainting_provider,
    landmark_provider=my_landmark_provider,
)

if result.compiler and result.compiler.qa.ready:
    a2d_bytes = result.compiler.artifact.a2d
```

The default ordering is:

```text
decompose → normalize → refine → complete → fuse landmarks → P2 compile
```

Debugging can independently disable refinement, completion or landmark fusion with:

```text
refine_semantics=False
complete_hidden=False
fuse_landmarks_enabled=False
```

## Tests

```bash
PYTHONPATH=services/decomposer:services/rig-compiler \
python -m unittest discover -s services/decomposer/tests -v
```

## Next

P3-R6 Quality Scoring:
- decompose/refinement/completion/landmark evidence aggregation
- stage scores
- release thresholds
- retry/manual-review recommendations
- stable quality report for Studio UI
