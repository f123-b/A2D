from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any

from .bridge import SingleImageCompileResultV1


class E2EMode(StrEnum):
    REFERENCE = "reference"
    PRODUCTION = "production"


class E2EGate(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


@dataclass(frozen=True, slots=True)
class RuntimeSmokeV1:
    passed: bool
    loader: str
    part_count: int = 0
    parameter_count: int = 0
    buffer_count: int = 0
    texture_count: int = 0
    error: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RuntimeSmokeV1":
        if not isinstance(value, dict):
            raise ValueError("runtime smoke payload must be an object")
        passed = value.get("passed")
        loader = value.get("loader")
        if not isinstance(passed, bool):
            raise ValueError("runtime smoke passed must be boolean")
        if not isinstance(loader, str) or not loader:
            raise ValueError("runtime smoke loader is required")
        counts: list[int] = []
        for key in ("partCount", "parameterCount", "bufferCount", "textureCount"):
            item = value.get(key, 0)
            if not isinstance(item, int) or item < 0:
                raise ValueError(f"runtime smoke {key} must be an integer >= 0")
            counts.append(item)
        error = value.get("error")
        if error is not None and not isinstance(error, str):
            raise ValueError("runtime smoke error must be a string when present")
        return cls(passed, loader, *counts, error)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "loader": self.loader,
            "partCount": self.part_count,
            "parameterCount": self.parameter_count,
            "bufferCount": self.buffer_count,
            "textureCount": self.texture_count,
            **({"error": self.error} if self.error is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class SingleImageE2EPreflightV1:
    version: int
    character_id: str
    mode: E2EMode
    source_sha256: str
    backend_name: str
    backend_revision: str
    completion_provider: str | None
    landmark_provider: str | None
    decomposer_ready: bool
    compiler_present: bool
    compiler_qa_ready: bool
    compiler_qa_score: int | None
    quality_decision: str | None
    quality_score: int | None
    ready_for_export: bool
    artifact_sha256: str | None
    artifact_byte_length: int

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "characterId": self.character_id,
            "mode": self.mode.value,
            "sourceSha256": self.source_sha256,
            "backend": {"name": self.backend_name, "revision": self.backend_revision},
            "completionProvider": self.completion_provider,
            "landmarkProvider": self.landmark_provider,
            "decomposerReady": self.decomposer_ready,
            "compilerPresent": self.compiler_present,
            "compilerQaReady": self.compiler_qa_ready,
            "compilerQaScore": self.compiler_qa_score,
            "qualityDecision": self.quality_decision,
            "qualityScore": self.quality_score,
            "readyForExport": self.ready_for_export,
            "artifactSha256": self.artifact_sha256,
            "artifactByteLength": self.artifact_byte_length,
        }


@dataclass(frozen=True, slots=True)
class SingleImageE2EReportV1:
    version: int
    character_id: str
    mode: E2EMode
    gate: E2EGate
    source_sha256: str
    backend_name: str
    backend_revision: str
    quality_decision: str | None
    quality_score: int | None
    ready_for_export: bool
    artifact_sha256: str | None
    artifact_byte_length: int
    runtime: RuntimeSmokeV1 | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "characterId": self.character_id,
            "mode": self.mode.value,
            "gate": self.gate.value,
            "sourceSha256": self.source_sha256,
            "backend": {"name": self.backend_name, "revision": self.backend_revision},
            "qualityDecision": self.quality_decision,
            "qualityScore": self.quality_score,
            "readyForExport": self.ready_for_export,
            "artifactSha256": self.artifact_sha256,
            "artifactByteLength": self.artifact_byte_length,
            "runtime": self.runtime.to_dict() if self.runtime is not None else None,
            "reasons": list(self.reasons),
        }


def provider_identity(provider: Any | None, *, kind: str) -> str | None:
    if provider is None:
        return None
    if kind == "completion":
        name = getattr(provider, "provider_name", None)
        revision = getattr(provider, "provider_revision", None)
    elif kind == "landmark":
        name = getattr(provider, "provider_name", None)
        revision = getattr(provider, "provider_revision", None)
    else:
        raise ValueError("provider kind must be completion or landmark")
    if isinstance(name, str) and name and isinstance(revision, str) and revision:
        return f"{name}@{revision}"
    return type(provider).__name__


def build_e2e_preflight(
    character_id: str,
    source_payload: bytes,
    result: SingleImageCompileResultV1,
    *,
    mode: E2EMode,
    backend_name: str,
    backend_revision: str,
    completion_provider: Any | None = None,
    landmark_provider: Any | None = None,
) -> SingleImageE2EPreflightV1:
    if not character_id:
        raise ValueError("character_id is required")
    if not source_payload:
        raise ValueError("source payload is required")
    if not backend_name or not backend_revision:
        raise ValueError("backend name/revision are required")

    compiler = result.compiler
    qa = getattr(compiler, "qa", None) if compiler is not None else None
    artifact = getattr(compiler, "artifact", None) if compiler is not None else None
    quality = result.quality
    artifact_bytes = getattr(artifact, "a2d", None) if artifact is not None else None
    artifact_sha = getattr(artifact, "sha256", None) if artifact is not None else None
    if artifact_bytes is not None and not isinstance(artifact_bytes, (bytes, bytearray)):
        raise TypeError("compiler artifact a2d must be bytes")
    if artifact_bytes is not None:
        computed = hashlib.sha256(bytes(artifact_bytes)).hexdigest()
        if artifact_sha is not None and artifact_sha != computed:
            raise ValueError("compiler artifact sha256 does not match a2d bytes")
        artifact_sha = computed

    return SingleImageE2EPreflightV1(
        version=1,
        character_id=character_id,
        mode=mode,
        source_sha256=hashlib.sha256(source_payload).hexdigest(),
        backend_name=backend_name,
        backend_revision=backend_revision,
        completion_provider=provider_identity(completion_provider, kind="completion"),
        landmark_provider=provider_identity(landmark_provider, kind="landmark"),
        decomposer_ready=bool(result.decomposer.ready),
        compiler_present=compiler is not None,
        compiler_qa_ready=bool(getattr(qa, "ready", False)),
        compiler_qa_score=(int(getattr(qa, "score")) if qa is not None else None),
        quality_decision=(quality.decision.value if quality is not None else None),
        quality_score=(quality.score if quality is not None else None),
        ready_for_export=bool(quality.ready_for_export) if quality is not None else False,
        artifact_sha256=artifact_sha,
        artifact_byte_length=len(artifact_bytes) if artifact_bytes is not None else 0,
    )


def write_e2e_preflight_bundle(
    output_dir: str | Path,
    preflight: SingleImageE2EPreflightV1,
    result: SingleImageCompileResultV1,
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "e2e-preflight.json").write_text(
        json.dumps(preflight.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if result.quality is not None:
        (root / "quality-report.json").write_text(
            json.dumps(result.quality.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if result.compiler is not None and getattr(result.compiler, "qa", None) is not None:
        (root / "compiler-qa.json").write_text(
            json.dumps(result.compiler.qa.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    artifact = getattr(result.compiler, "artifact", None) if result.compiler is not None else None
    if artifact is not None:
        (root / "character.a2d").write_bytes(artifact.a2d)
    return root


def _preflight_from_dict(value: dict[str, object]) -> SingleImageE2EPreflightV1:
    backend = value.get("backend")
    if not isinstance(backend, dict):
        raise ValueError("preflight backend must be an object")
    mode = value.get("mode")
    return SingleImageE2EPreflightV1(
        version=int(value.get("version", 0)),
        character_id=str(value.get("characterId", "")),
        mode=E2EMode(str(mode)),
        source_sha256=str(value.get("sourceSha256", "")),
        backend_name=str(backend.get("name", "")),
        backend_revision=str(backend.get("revision", "")),
        completion_provider=(
            value.get("completionProvider")
            if isinstance(value.get("completionProvider"), str)
            else None
        ),
        landmark_provider=(
            value.get("landmarkProvider")
            if isinstance(value.get("landmarkProvider"), str)
            else None
        ),
        decomposer_ready=bool(value.get("decomposerReady", False)),
        compiler_present=bool(value.get("compilerPresent", False)),
        compiler_qa_ready=bool(value.get("compilerQaReady", False)),
        compiler_qa_score=(
            int(value["compilerQaScore"])
            if isinstance(value.get("compilerQaScore"), int)
            else None
        ),
        quality_decision=(
            value.get("qualityDecision")
            if isinstance(value.get("qualityDecision"), str)
            else None
        ),
        quality_score=(
            int(value["qualityScore"])
            if isinstance(value.get("qualityScore"), int)
            else None
        ),
        ready_for_export=bool(value.get("readyForExport", False)),
        artifact_sha256=(
            value.get("artifactSha256")
            if isinstance(value.get("artifactSha256"), str)
            else None
        ),
        artifact_byte_length=int(value.get("artifactByteLength", 0)),
    )


def finalize_e2e_bundle(output_dir: str | Path) -> SingleImageE2EReportV1:
    root = Path(output_dir)
    preflight_path = root / "e2e-preflight.json"
    if not preflight_path.is_file():
        raise ValueError("e2e-preflight.json is missing")
    preflight = _preflight_from_dict(json.loads(preflight_path.read_text(encoding="utf-8")))

    runtime: RuntimeSmokeV1 | None = None
    runtime_path = root / "runtime-smoke.json"
    if runtime_path.is_file():
        runtime = RuntimeSmokeV1.from_dict(
            json.loads(runtime_path.read_text(encoding="utf-8"))
        )

    reasons: list[str] = []
    if not preflight.decomposer_ready:
        reasons.append("decomposer_not_ready")
    if not preflight.compiler_present:
        reasons.append("compiler_missing")
    if not preflight.compiler_qa_ready:
        reasons.append("compiler_qa_not_ready")
    if preflight.quality_decision != "pass" or not preflight.ready_for_export:
        reasons.append("quality_not_pass")
    if not preflight.artifact_sha256 or preflight.artifact_byte_length <= 0:
        reasons.append("artifact_missing")
    if preflight.mode is E2EMode.PRODUCTION and preflight.backend_name != "see-through":
        reasons.append("production_backend_not_see_through")

    if runtime is None:
        gate = E2EGate.NOT_RUN
        reasons.append("runtime_smoke_not_run")
    elif not runtime.passed:
        gate = E2EGate.FAIL
        reasons.append("runtime_loader_failed")
    elif reasons:
        gate = E2EGate.FAIL
    else:
        gate = E2EGate.PASS

    report = SingleImageE2EReportV1(
        version=1,
        character_id=preflight.character_id,
        mode=preflight.mode,
        gate=gate,
        source_sha256=preflight.source_sha256,
        backend_name=preflight.backend_name,
        backend_revision=preflight.backend_revision,
        quality_decision=preflight.quality_decision,
        quality_score=preflight.quality_score,
        ready_for_export=preflight.ready_for_export,
        artifact_sha256=preflight.artifact_sha256,
        artifact_byte_length=preflight.artifact_byte_length,
        runtime=runtime,
        reasons=tuple(sorted(set(reasons))),
    )
    (root / "e2e-report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
