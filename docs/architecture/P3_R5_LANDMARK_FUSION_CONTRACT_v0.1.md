# P3-R5 Landmark Fusion Contract v0.1

## Goal

Produce one deterministic canonical landmark set for Phase 2 without coupling the rig compiler to a particular face-landmark model.

Pipeline:

```text
existing backend landmarks
          +
LandmarkProvider candidates
          +
semantic-layer geometry
          ↓
canonicalization
          ↓
confidence/disagreement fusion
          ↓
NormalizedLandmarkV1[]
          ↓
P2 Semantic Rig / Proxy-Z / Physics
```

## Provider contract

A production provider implements:

```python
class LandmarkProvider(Protocol):
    provider_name: str
    provider_revision: str

    def infer_landmarks(
        self,
        image: SourceImageRgba,
        result: DecomposerResultV1,
    ) -> tuple[LandmarkCandidateV1, ...]: ...
```

`LandmarkCandidateV1` coordinates are normalized to the original source canvas `[0,1]`.

Provider identity is mandatory because name/revision participates in `sourceRevision`.

## Canonical vocabulary

P3-R5 targets the P2 pivot/depth vocabulary:

```text
head_center
nose
neck
eye_l_center
eye_r_center
iris_l_center
iris_r_center
mouth_center
brow_l_center
brow_r_center
hair_front_root
hair_side_l_root
hair_side_r_root
hair_back_root
```

Provider aliases are normalized through the existing P3 landmark vocabulary.

## Geometry evidence

Geometry fallback is derived only from retained semantic pixels.

Facial part centers use alpha-weighted centroids, not bbox centers.

Hair roots use the alpha-weighted centroid of the top active band of each hair layer, keeping spring-chain roots near the attachment region.

`head_center` comes from the face alpha centroid.

`nose` is a conservative face-relative estimate when no direct evidence exists.

`neck` is estimated from the face/body transition and receives lower confidence than directly detected facial centers.

No landmark is generated for a missing semantic layer except the face-relative nose/neck rules where the required source layers exist.

## Fusion policy

Each evidence source has a reliability weight:

```text
existing = 1.00
provider = 1.10
geometry = 0.65
```

Rules:

1. existing confidence >= 0.90 is preserved exactly;
2. agreeing candidates use confidence × reliability weighted position fusion;
3. fused confidence remains conservative, with only a small agreement bonus;
4. candidates separated by more than `0.18 × face diagonal` are considered disagreeing;
5. disagreement selects the strongest weighted candidate instead of averaging incompatible points;
6. disagreement applies a confidence penalty and emits `landmark-disagreement`;
7. final confidence below 0.65 emits `landmark-low-confidence`.

P3-R1 low-confidence findings are re-evaluated against the fused output rather than remaining stale.

## Provider failure

A supplied provider is part of the requested production path. Therefore these are blocking:

- provider exception;
- invalid provider identity;
- non-tuple provider output;
- invalid candidate coordinates/confidence;
- duplicate canonical provider landmarks.

Unsupported landmark labels are informational and ignored.

## Determinism

Output order is canonical landmark ID order. `sourceRevision` hashes:

- previous revision;
- `LandmarkFusionConfig`;
- provider name;
- provider revision;
- P3-R5 contract version.

For the same normalized layers, assets, provider outputs and config, landmarks/findings/revision must be identical.

## Phase-2 compatibility

No Phase-2 ABI changes are introduced.

The current P2 consumers already understand these IDs:

- Semantic Rig pivots use neck/head/eye/iris/mouth/brow/hair-root landmarks;
- Proxy-Z uses head center, eye centers, nose and mouth;
- Auto Physics uses semantic hair root pivots.

The P3→P2 bridge continues to convert `NormalizedLandmarkV1` directly into the existing `Landmark` type.
