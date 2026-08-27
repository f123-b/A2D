# P3-R4 Occlusion Completion Contract v0.1

## Goal

Add a provider-agnostic hidden-pixel completion stage between semantic refinement and the Phase-2 rig compiler, without allowing a generative model to rewrite already observed character pixels.

## Pipeline

```text
Refined semantic layers
        ↓
semantic occluder projection
        ↓
completion mask
        ↓
CompletionProvider
        ↓
provider output validation
        ↓
completed RGBA/A8
        ↓
P2 compile_avatar()
```

## CompletionProvider ABI

A provider exposes `provider_name`, `provider_revision`, and implements:

```python
complete(request: CompletionRequestV1) -> CompletionResponseV1
```

The request contains target semantic/id, normalized bbox, target dimensions, visible RGBA/A8, an explicit completion mask and the full source RGBA image. The response contains target-sized RGBA and confidence in `[0,1]`.

## Visible-pixel invariant

For every pixel where `completion_mask == 0`, provider output must remain byte-identical to visible input RGBA. Mutation outside the allowed mask is a blocking `completion-visible-pixel-mutated` error.

## Mask derivation v1

### Face

Occluders: `hair_front`, `hair_side_l`, `hair_side_r`. A face pixel is completable only when face alpha is low and projected hair alpha is active at the same source-space position.

### Body

A normal body layer uses `cloth` as v1 occluder. A P3-R3 `body-proxy-synthesized` target is not considered observed anatomy; when enabled, its full local target is marked for completion.

## Failure policy

No provider emits `completion-provider-missing` warning and preserves refined pixels. Invalid supplied providers block release through `completion-provider-error`, `completion-output-size-invalid`, `completion-confidence-invalid`, or `completion-visible-pixel-mutated`.

Successful completion merges alpha only inside the completion mask, emits `occlusion-completed`, and reports `completion-low-confidence` when provider confidence is below the configured threshold.

## Reference provider

`DeterministicReferenceCompletionProvider` is a correctness oracle, not a production visual model. It uses deterministic nearest-visible-pixel propagation and a neutral fallback when no protected seed exists. Its confidence is intentionally 0.50.

## Determinism

Revision hashes previous source revision, completion configuration, provider identity/revision and the P3-R4 contract version. Reference fill, projected masks, finding order and asset order are deterministic.

## Non-goals

- no claim of production-quality generative inpainting in CI
- no landmark inference
- no bbox expansion beyond the refined target in v0.1
- no creation of a completely absent face/body semantic
- no visible-pixel rewriting by any provider
