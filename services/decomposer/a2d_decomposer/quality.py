from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any

from .contract import DecomposerResultV1


class QualityDecision(StrEnum):
    PASS = "pass"
    RETRY = "retry"
    MANUAL_REVIEW = "manual_review"
    BLOCK = "block"


class QualityDimension(StrEnum):
    SEMANTIC = "semantic"
    COMPLETION = "completion"
    LANDMARK = "landmark"
    CONSISTENCY = "consistency"
    SYNTHETIC = "synthetic"
    COMPILER = "compiler"


class QualityActionKind(StrEnum):
    RERUN_DECOMPOSITION = "rerun_decomposition"
    RUN_COMPLETION = "run_completion"
    RUN_LANDMARK_PROVIDER = "run_landmark_provider"
    REVIEW_SEMANTICS = "review_semantics"
    REVIEW_LANDMARKS = "review_landmarks"
    REVIEW_COMPILER = "review_compiler"
    FIX_COMPILER = "fix_compiler"


@dataclass(frozen=True, slots=True)
class QualityFindingV1:
    severity: str
    dimension: QualityDimension
    code: str
    message: str
    penalty: int = 0
    subject_id: str | None = None


@dataclass(frozen=True, slots=True)
class QualityDimensionScoreV1:
    dimension: QualityDimension
    score: int
    weight: int


@dataclass(frozen=True, slots=True)
class QualityActionV1:
    kind: QualityActionKind
    code: str
    priority: str
    automatic: bool
    message: str
    subject_id: str | None = None


@dataclass(frozen=True, slots=True)
class CharacterQualityReportV1:
    version: int
    character_id: str
    decision: QualityDecision
    score: int
    ready_for_export: bool
    errors: int
    warnings: int
    infos: int
    dimensions: tuple[QualityDimensionScoreV1, ...]
    findings: tuple[QualityFindingV1, ...]
    actions: tuple[QualityActionV1, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "characterId": self.character_id,
            "decision": self.decision.value,
            "score": self.score,
            "readyForExport": self.ready_for_export,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos,
            "dimensions": [
                {
                    "dimension": item.dimension.value,
                    "score": item.score,
                    "weight": item.weight,
                }
                for item in self.dimensions
            ],
            "findings": [
                {
                    "severity": item.severity,
                    "dimension": item.dimension.value,
                    "code": item.code,
                    "message": item.message,
                    "penalty": item.penalty,
                    **(
                        {"subjectId": item.subject_id}
                        if item.subject_id is not None
                        else {}
                    ),
                }
                for item in self.findings
            ],
            "actions": [
                {
                    "kind": item.kind.value,
                    "code": item.code,
                    "priority": item.priority,
                    "automatic": item.automatic,
                    "message": item.message,
                    **(
                        {"subjectId": item.subject_id}
                        if item.subject_id is not None
                        else {}
                    ),
                }
                for item in self.actions
            ],
        }


@dataclass(frozen=True, slots=True)
class QualityScoringConfig:
    pass_score: int = 85
    manual_review_score: int = 70
    low_layer_confidence_threshold: float = 0.65
    low_landmark_confidence_threshold: float = 0.65
    semantic_weight: int = 25
    completion_weight: int = 20
    landmark_weight: int = 20
    consistency_weight: int = 10
    synthetic_weight: int = 10
    compiler_weight: int = 15

    def validate(self) -> None:
        if not 0 <= self.manual_review_score < self.pass_score <= 100:
            raise ValueError(
                "quality score thresholds must satisfy "
                "0 <= manual_review_score < pass_score <= 100"
            )
        for name, value in (
            ("low_layer_confidence_threshold", self.low_layer_confidence_threshold),
            ("low_landmark_confidence_threshold", self.low_landmark_confidence_threshold),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite in [0,1]")
        weights = (
            self.semantic_weight,
            self.completion_weight,
            self.landmark_weight,
            self.consistency_weight,
            self.synthetic_weight,
            self.compiler_weight,
        )
        if any(not isinstance(value, int) or value < 0 for value in weights):
            raise ValueError("quality dimension weights must be non-negative integers")
        if sum(weights) != 100:
            raise ValueError("quality dimension weights must sum to 100")


_REQUIRED_SEMANTICS: tuple[str, ...] = (
    "body",
    "face",
    "eye_white_l",
    "eye_white_r",
    "iris_l",
    "iris_r",
    "mouth",
)

_BASE_LANDMARKS: tuple[str, ...] = (
    "head_center",
    "nose",
    "neck",
    "eye_l_center",
    "eye_r_center",
    "iris_l_center",
    "iris_r_center",
    "mouth_center",
)

_OPTIONAL_LANDMARK_BY_SEMANTIC: tuple[tuple[str, str], ...] = (
    ("brow_l", "brow_l_center"),
    ("brow_r", "brow_r_center"),
    ("hair_front", "hair_front_root"),
    ("hair_side_l", "hair_side_l_root"),
    ("hair_side_r", "hair_side_r_root"),
    ("hair_back", "hair_back_root"),
)

_DIMENSION_ORDER: tuple[QualityDimension, ...] = tuple(QualityDimension)
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_ACTION_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(math.floor(value + 0.5))))


def _finding_dimension(code: str) -> QualityDimension:
    if code.startswith("completion-") or code.startswith("occlusion-completion"):
        return QualityDimension.COMPLETION
    if code.startswith("landmark-"):
        return QualityDimension.LANDMARK
    if code in {
        "body-proxy-synthesized",
        "semantic-pair-mirrored",
        "side-hair-synthesized",
    }:
        return QualityDimension.SYNTHETIC
    if code in {
        "semantic-pair-geometry-mismatch",
        "semantic-pair-confidence-mismatch",
        "semantic-z-order-corrected",
    }:
        return QualityDimension.CONSISTENCY
    return QualityDimension.SEMANTIC


def _append_action(
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
    action: QualityActionV1,
) -> None:
    key = (action.kind, action.subject_id)
    current = actions.get(key)
    if current is None:
        actions[key] = action
        return
    if _ACTION_PRIORITY_ORDER.get(action.priority, 99) < _ACTION_PRIORITY_ORDER.get(
        current.priority, 99
    ):
        actions[key] = action


def _semantic_score(
    result: DecomposerResultV1,
    config: QualityScoringConfig,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> int:
    by_semantic = {
        item.semantic: item
        for item in result.layers
        if item.semantic != "accessory"
    }
    confidences: list[float] = []
    for semantic in _REQUIRED_SEMANTICS:
        layer = by_semantic.get(semantic)
        if layer is None:
            confidences.append(0.0)
            subject = semantic.replace("_", "-")
            findings.append(QualityFindingV1(
                "error", QualityDimension.SEMANTIC,
                "quality-required-semantic-missing",
                f"required semantic {semantic} is missing", 100, subject,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.RERUN_DECOMPOSITION,
                "rerun-decomposition", "high", True,
                f"rerun decomposition to recover required semantic {semantic}", subject,
            ))
            continue
        confidences.append(layer.confidence)
        if layer.confidence < config.low_layer_confidence_threshold:
            penalty = _clamp_score(
                (config.low_layer_confidence_threshold - layer.confidence) * 50
            )
            findings.append(QualityFindingV1(
                "warning", QualityDimension.SEMANTIC,
                "quality-layer-low-confidence",
                f"{semantic} confidence {layer.confidence:.3f} is below "
                f"{config.low_layer_confidence_threshold:.3f}",
                penalty, layer.id,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.RERUN_DECOMPOSITION,
                "rerun-decomposition", "medium", True,
                f"rerun decomposition for low-confidence {semantic}", layer.id,
            ))
    return _clamp_score(sum(confidences) / len(confidences) * 100.0)


def _completion_score(
    result: DecomposerResultV1,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> int:
    required = {
        item.subject_id
        for item in result.findings
        if item.code == "occlusion-completion-required"
        and item.subject_id is not None
    }
    if not required:
        return 100

    completed = {
        item.subject_id
        for item in result.findings
        if item.code == "occlusion-completed" and item.subject_id is not None
    }
    provider_missing = {
        item.subject_id
        for item in result.findings
        if item.code == "completion-provider-missing" and item.subject_id is not None
    }
    low_confidence = {
        item.subject_id
        for item in result.findings
        if item.code == "completion-low-confidence" and item.subject_id is not None
    }

    target_scores: list[int] = []
    for subject in sorted(required):
        if subject in completed:
            if subject in low_confidence:
                target_scores.append(55)
                findings.append(QualityFindingV1(
                    "warning", QualityDimension.COMPLETION,
                    "quality-completion-low-confidence",
                    f"{subject} completion is low confidence", 45, subject,
                ))
                _append_action(actions, QualityActionV1(
                    QualityActionKind.RUN_COMPLETION,
                    "rerun-completion", "high", True,
                    f"rerun completion for {subject} with a stronger provider", subject,
                ))
            else:
                target_scores.append(100)
        elif subject in provider_missing:
            target_scores.append(35)
            findings.append(QualityFindingV1(
                "warning", QualityDimension.COMPLETION,
                "quality-completion-provider-missing",
                f"{subject} requires completion but no provider completed it",
                65, subject,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.RUN_COMPLETION,
                "run-completion", "high", True,
                f"run an occlusion completion provider for {subject}", subject,
            ))
        else:
            target_scores.append(20)
            findings.append(QualityFindingV1(
                "warning", QualityDimension.COMPLETION,
                "quality-completion-unresolved",
                f"{subject} requires completion and remains unresolved", 80, subject,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.RUN_COMPLETION,
                "run-completion", "high", True,
                f"rerun occlusion completion for {subject}", subject,
            ))
    return _clamp_score(sum(target_scores) / len(target_scores))


def _expected_landmarks(result: DecomposerResultV1) -> tuple[str, ...]:
    semantics = {item.semantic for item in result.layers}
    expected = list(_BASE_LANDMARKS)
    for semantic, landmark_id in _OPTIONAL_LANDMARK_BY_SEMANTIC:
        if semantic in semantics:
            expected.append(landmark_id)
    return tuple(expected)


def _landmark_score(
    result: DecomposerResultV1,
    config: QualityScoringConfig,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> int:
    table = {item.id: item for item in result.landmarks}
    expected = _expected_landmarks(result)
    confidences: list[float] = []
    for landmark_id in expected:
        landmark = table.get(landmark_id)
        if landmark is None:
            confidences.append(0.0)
            findings.append(QualityFindingV1(
                "warning", QualityDimension.LANDMARK,
                "quality-landmark-missing",
                f"{landmark_id} is missing and Phase 2 will use a fallback",
                20, landmark_id,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.RUN_LANDMARK_PROVIDER,
                "run-landmark-provider", "medium", True,
                f"run a landmark provider to recover {landmark_id}", landmark_id,
            ))
            continue
        confidences.append(landmark.confidence)
        if landmark.confidence < config.low_landmark_confidence_threshold:
            penalty = _clamp_score(
                (config.low_landmark_confidence_threshold - landmark.confidence) * 50
            )
            findings.append(QualityFindingV1(
                "warning", QualityDimension.LANDMARK,
                "quality-landmark-low-confidence",
                f"{landmark_id} confidence {landmark.confidence:.3f} is below "
                f"{config.low_landmark_confidence_threshold:.3f}",
                penalty, landmark_id,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.RUN_LANDMARK_PROVIDER,
                "run-landmark-provider", "medium", True,
                f"run a landmark provider to improve {landmark_id}", landmark_id,
            ))

    score = _clamp_score(sum(confidences) / len(confidences) * 100.0)
    disagreement_count = sum(
        1 for item in result.findings if item.code == "landmark-disagreement"
    )
    if disagreement_count:
        disagreement_penalty = min(30, disagreement_count * 8)
        score = max(0, score - disagreement_penalty)
        findings.append(QualityFindingV1(
            "warning", QualityDimension.LANDMARK,
            "quality-landmark-disagreement",
            f"{disagreement_count} landmark candidate set(s) disagree",
            disagreement_penalty, None,
        ))
        _append_action(actions, QualityActionV1(
            QualityActionKind.REVIEW_LANDMARKS,
            "review-landmarks", "medium", False,
            "review landmarks with disagreement before automatic export", None,
        ))
    return score


def _consistency_score(
    result: DecomposerResultV1,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> int:
    penalty_by_code = {
        "semantic-pair-geometry-mismatch": 20,
        "semantic-pair-confidence-mismatch": 10,
        "semantic-z-order-corrected": 5,
    }
    penalty = 0
    for item in result.findings:
        amount = penalty_by_code.get(item.code)
        if amount is None:
            continue
        penalty += amount
        findings.append(QualityFindingV1(
            "warning", QualityDimension.CONSISTENCY,
            f"quality-{item.code}", item.message, amount, item.subject_id,
        ))
        if item.code != "semantic-z-order-corrected":
            _append_action(actions, QualityActionV1(
                QualityActionKind.REVIEW_SEMANTICS,
                "review-semantic-consistency", "medium", False,
                "review paired semantic geometry/confidence before export",
                item.subject_id,
            ))
    return max(0, 100 - min(100, penalty))


def _synthetic_score(
    result: DecomposerResultV1,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> int:
    completed = {
        item.subject_id
        for item in result.findings
        if item.code == "occlusion-completed" and item.subject_id is not None
    }
    penalty = 0
    for item in result.findings:
        amount = 0
        if item.code == "body-proxy-synthesized":
            amount = 15 if "body" in completed else 35
        elif item.code == "semantic-pair-mirrored":
            amount = 12
        elif item.code == "side-hair-synthesized":
            amount = 8
        if amount == 0:
            continue
        penalty += amount
        findings.append(QualityFindingV1(
            "warning", QualityDimension.SYNTHETIC,
            f"quality-{item.code}", item.message, amount, item.subject_id,
        ))
        _append_action(actions, QualityActionV1(
            QualityActionKind.REVIEW_SEMANTICS,
            "review-synthetic-semantic",
            "low" if item.code == "side-hair-synthesized" else "medium",
            False,
            "review synthesized semantic content before final export",
            item.subject_id,
        ))
    return max(0, 100 - min(100, penalty))


def _compiler_score(
    compiler: Any | None,
    upstream_ready: bool,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> tuple[int, bool]:
    if compiler is None:
        if upstream_ready:
            findings.append(QualityFindingV1(
                "error", QualityDimension.COMPILER,
                "quality-compiler-missing",
                "Phase-2 compiler result is unavailable", 100, None,
            ))
            _append_action(actions, QualityActionV1(
                QualityActionKind.FIX_COMPILER,
                "fix-compiler", "high", False,
                "repair the P3 to P2 compiler integration", None,
            ))
        else:
            findings.append(QualityFindingV1(
                "info", QualityDimension.COMPILER,
                "quality-compiler-skipped",
                "Phase-2 compilation was skipped because upstream P3 is blocked",
                0, None,
            ))
        return 0, False

    qa = getattr(compiler, "qa", None)
    if qa is None:
        findings.append(QualityFindingV1(
            "error", QualityDimension.COMPILER,
            "quality-compiler-qa-missing",
            "Phase-2 compiler result has no QA report", 100, None,
        ))
        _append_action(actions, QualityActionV1(
            QualityActionKind.FIX_COMPILER,
            "fix-compiler", "high", False,
            "repair compiler QA integration", None,
        ))
        return 0, False

    ready = bool(getattr(qa, "ready", False))
    raw_score = getattr(qa, "score", 0)
    if not isinstance(raw_score, (int, float)) or not math.isfinite(float(raw_score)):
        raw_score = 0
    score = _clamp_score(float(raw_score))
    if not ready:
        findings.append(QualityFindingV1(
            "error", QualityDimension.COMPILER,
            "quality-compiler-qa-blocked",
            "Phase-2 compiler QA is not ready", max(0, 100 - score), None,
        ))
        _append_action(actions, QualityActionV1(
            QualityActionKind.FIX_COMPILER,
            "fix-compiler", "high", False,
            "resolve Phase-2 compiler QA errors", None,
        ))
    elif score < 85:
        findings.append(QualityFindingV1(
            "warning", QualityDimension.COMPILER,
            "quality-compiler-score-low",
            f"Phase-2 compiler QA score is {score}/100", 100 - score, None,
        ))
        _append_action(actions, QualityActionV1(
            QualityActionKind.REVIEW_COMPILER,
            "review-compiler-qa", "medium", False,
            "review Phase-2 QA warnings before final export", None,
        ))
    return score, ready


def _surface_source_errors(
    result: DecomposerResultV1,
    findings: list[QualityFindingV1],
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1],
) -> bool:
    blocked = False
    for item in result.findings:
        if item.severity != "error":
            continue
        blocked = True
        dimension = _finding_dimension(item.code)
        findings.append(QualityFindingV1(
            "error", dimension, f"source-{item.code}",
            item.message, 100, item.subject_id,
        ))
        if dimension is QualityDimension.COMPLETION:
            action = QualityActionV1(
                QualityActionKind.RUN_COMPLETION,
                "repair-completion-provider", "high", True,
                "repair or replace the completion provider and retry",
                item.subject_id,
            )
        elif dimension is QualityDimension.LANDMARK:
            action = QualityActionV1(
                QualityActionKind.RUN_LANDMARK_PROVIDER,
                "repair-landmark-provider", "high", True,
                "repair or replace the landmark provider and retry",
                item.subject_id,
            )
        else:
            action = QualityActionV1(
                QualityActionKind.RERUN_DECOMPOSITION,
                "rerun-decomposition", "high", True,
                "rerun decomposition after resolving the blocking semantic input",
                item.subject_id,
            )
        _append_action(actions, action)
    return blocked


def score_character_quality(
    result: DecomposerResultV1,
    compiler: Any | None,
    *,
    config: QualityScoringConfig | None = None,
) -> CharacterQualityReportV1:
    """Build a deterministic release-quality report from P3 and P2 evidence."""
    config = config or QualityScoringConfig()
    config.validate()
    if not result.character_id:
        raise ValueError("quality scoring requires character_id")

    findings: list[QualityFindingV1] = []
    actions: dict[tuple[QualityActionKind, str | None], QualityActionV1] = {}

    source_blocked = _surface_source_errors(result, findings, actions)
    semantic = _semantic_score(result, config, findings, actions)
    completion = _completion_score(result, findings, actions)
    landmark = _landmark_score(result, config, findings, actions)
    consistency = _consistency_score(result, findings, actions)
    synthetic = _synthetic_score(result, findings, actions)
    compiler_score, compiler_ready = _compiler_score(
        compiler, result.ready, findings, actions
    )

    scores = {
        QualityDimension.SEMANTIC: semantic,
        QualityDimension.COMPLETION: completion,
        QualityDimension.LANDMARK: landmark,
        QualityDimension.CONSISTENCY: consistency,
        QualityDimension.SYNTHETIC: synthetic,
        QualityDimension.COMPILER: compiler_score,
    }
    weights = {
        QualityDimension.SEMANTIC: config.semantic_weight,
        QualityDimension.COMPLETION: config.completion_weight,
        QualityDimension.LANDMARK: config.landmark_weight,
        QualityDimension.CONSISTENCY: config.consistency_weight,
        QualityDimension.SYNTHETIC: config.synthetic_weight,
        QualityDimension.COMPILER: config.compiler_weight,
    }
    weighted = sum(
        scores[key] * weights[key]
        for key in _DIMENSION_ORDER
    ) / 100.0
    score = _clamp_score(weighted)

    retry_kinds = {
        QualityActionKind.RERUN_DECOMPOSITION,
        QualityActionKind.RUN_COMPLETION,
        QualityActionKind.RUN_LANDMARK_PROVIDER,
    }
    manual_kinds = {
        QualityActionKind.REVIEW_SEMANTICS,
        QualityActionKind.REVIEW_LANDMARKS,
        QualityActionKind.REVIEW_COMPILER,
    }
    action_values = tuple(actions.values())
    has_retry = any(item.kind in retry_kinds for item in action_values)
    has_manual = any(item.kind in manual_kinds for item in action_values)

    if source_blocked or not result.ready or not compiler_ready:
        decision = QualityDecision.BLOCK
    elif has_retry:
        decision = QualityDecision.RETRY
    elif has_manual:
        decision = QualityDecision.MANUAL_REVIEW
    elif score >= config.pass_score:
        decision = QualityDecision.PASS
    elif score >= config.manual_review_score:
        decision = QualityDecision.MANUAL_REVIEW
    else:
        decision = QualityDecision.RETRY

    findings.sort(key=lambda item: (
        _SEVERITY_ORDER.get(item.severity, 3),
        _DIMENSION_ORDER.index(item.dimension),
        item.code,
        item.subject_id or "",
        item.message,
    ))
    sorted_actions = sorted(action_values, key=lambda item: (
        _ACTION_PRIORITY_ORDER.get(item.priority, 99),
        item.kind.value,
        item.code,
        item.subject_id or "",
    ))
    dimensions = tuple(
        QualityDimensionScoreV1(key, scores[key], weights[key])
        for key in _DIMENSION_ORDER
    )
    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    infos = sum(item.severity == "info" for item in findings)
    return CharacterQualityReportV1(
        1,
        result.character_id,
        decision,
        score,
        decision is QualityDecision.PASS,
        errors,
        warnings,
        infos,
        dimensions,
        tuple(findings),
        tuple(sorted_actions),
    )
