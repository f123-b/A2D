# A2D Decomposer

Phase 3 converts one flat source image into the normalized semantic-layer package consumed by the Phase-2 rig compiler.

## P3-R1 boundary

```text
SourceImageRgba
      ↓
DecompositionBackend
      ↓
BackendDecompositionV1 observations
      ↓
normalize_backend_output()
      ↓
Normalized semantic package + cropped RGBA/A8 assets + findings
```

P3-R1 deliberately does **not** embed See-through, SAM, MediaPipe, or any other model API into downstream code. A real AI integration only implements the `DecompositionBackend` protocol.

The zero-dependency `ScriptedReferenceBackend` is the correctness oracle for adapter development and CI.

### Normalization rules

- semantic aliases normalize to the Phase-2 vocabulary
- non-accessory canonical semantics are unique; duplicates are rejected
- multiple accessories are allowed and receive deterministic IDs
- masks are cropped to their active alpha bounds
- RGBA alpha is multiplied by the segmentation mask before export
- image/mask assets are emitted as deterministic package-relative `.rgba` / `.a8` resources
- pixel-space bounds and landmarks become normalized `[0,1]` coordinates
- unknown semantic/landmark labels are reported explicitly rather than silently mapped
- low-confidence layers/landmarks remain usable but generate warnings
- unresolved/cyclic parent graphs are rejected
- `sourceRevision` hashes source pixels + backend identity/revision

Run tests:

```bash
PYTHONPATH=services/decomposer \
python -m unittest discover -s services/decomposer/tests -v
```

## Next

P3-R2 adds the first real model adapter and single-image orchestration:

```text
PNG/JPG decode
  → person/part segmentation
  → face landmarks
  → semantic observations
  → P3-R1 normalization
  → P2 compile_avatar()
  → .a2d
```
