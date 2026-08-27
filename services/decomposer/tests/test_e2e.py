from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from a2d_decomposer import DecomposerResultV1, QualityDecision
from a2d_decomposer.bridge import SingleImageCompileResultV1
from a2d_decomposer.e2e import (
    E2EGate,
    E2EMode,
    RuntimeSmokeV1,
    build_e2e_preflight,
    finalize_e2e_bundle,
    provider_identity,
    write_e2e_preflight_bundle,
)


class FakeQa:
    def __init__(self, ready: bool = True, score: int = 100) -> None:
        self.ready = ready
        self.score = score

    def to_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "score": self.score}


class FakeArtifact:
    def __init__(self, payload: bytes = b"PK\x03\x04a2d") -> None:
        self.a2d = payload
        self.sha256 = hashlib.sha256(payload).hexdigest()


class FakeCompiler:
    def __init__(self, *, ready: bool = True, score: int = 100, artifact: bool = True) -> None:
        self.qa = FakeQa(ready, score)
        self.artifact = FakeArtifact() if artifact else None


@dataclass(frozen=True)
class FakeQuality:
    decision: QualityDecision = QualityDecision.PASS
    score: int = 96
    ready_for_export: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "score": self.score,
            "readyForExport": self.ready_for_export,
        }


class FakeProvider:
    provider_name = "provider"
    provider_revision = "7"


def decomposer(ready: bool = True) -> DecomposerResultV1:
    findings = () if ready else ()
    return DecomposerResultV1(
        1, "e2e", "sha256:source", 128, 128, (), (), (), findings
    )


def result(
    *,
    decomposer_ready: bool = True,
    compiler: FakeCompiler | None = None,
    quality: FakeQuality | None = None,
) -> SingleImageCompileResultV1:
    return SingleImageCompileResultV1(
        decomposer(decomposer_ready),
        compiler if compiler is not None else FakeCompiler(),
        quality if quality is not None else FakeQuality(),
    )


def smoke(*, passed: bool = True) -> dict[str, object]:
    return RuntimeSmokeV1(
        passed,
        "@a2d/runtime-api/loadA2DFromZip",
        13,
        21,
        1,
        1,
        None if passed else "loader rejected package",
    ).to_dict()


class SingleImageE2ETests(unittest.TestCase):
    def test_preflight_hashes_source_and_artifact(self) -> None:
        payload = b"source-image"
        value = build_e2e_preflight(
            "e2e", payload, result(),
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        self.assertEqual(value.source_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(value.artifact_sha256, hashlib.sha256(b"PK\x03\x04a2d").hexdigest())
        self.assertGreater(value.artifact_byte_length, 0)

    def test_provider_identity_uses_name_and_revision(self) -> None:
        self.assertEqual(provider_identity(FakeProvider(), kind="completion"), "provider@7")
        self.assertEqual(provider_identity(None, kind="landmark"), None)

    def test_write_bundle_preserves_preview_artifact_and_reports(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            self.assertTrue((root / "character.a2d").is_file())
            self.assertTrue((root / "quality-report.json").is_file())
            self.assertTrue((root / "compiler-qa.json").is_file())
            self.assertTrue((root / "e2e-preflight.json").is_file())

    def test_finalize_without_runtime_is_not_run(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            write_e2e_preflight_bundle(temp, preflight, compile_result)
            report = finalize_e2e_bundle(temp)
            self.assertEqual(report.gate, E2EGate.NOT_RUN)
            self.assertIn("runtime_smoke_not_run", report.reasons)

    def test_reference_gate_passes_after_runtime_loader(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.PASS)
            self.assertEqual(report.reasons, ())

    def test_runtime_loader_failure_fails_gate(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke(passed=False)), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.FAIL)
            self.assertIn("runtime_loader_failed", report.reasons)

    def test_quality_retry_fails_release_gate_but_keeps_artifact(self) -> None:
        compile_result = result(quality=FakeQuality(QualityDecision.RETRY, 72, False))
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.FAIL)
            self.assertTrue((root / "character.a2d").is_file())
            self.assertIn("quality_not_pass", report.reasons)

    def test_compiler_qa_failure_fails_gate(self) -> None:
        compile_result = result(compiler=FakeCompiler(ready=False, score=20))
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.FAIL)
            self.assertIn("compiler_qa_not_ready", report.reasons)

    def test_missing_artifact_fails_gate(self) -> None:
        compile_result = result(compiler=FakeCompiler(artifact=False))
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.FAIL)
            self.assertIn("artifact_missing", report.reasons)

    def test_production_gate_requires_see_through_backend(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.PRODUCTION,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.FAIL)
            self.assertIn("production_backend_not_see_through", report.reasons)

    def test_production_gate_accepts_see_through_evidence(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.PRODUCTION,
            backend_name="see-through",
            backend_revision="pinned-revision",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            report = finalize_e2e_bundle(root)
            self.assertEqual(report.gate, E2EGate.PASS)

    def test_final_report_is_stable_json(self) -> None:
        compile_result = result()
        preflight = build_e2e_preflight(
            "e2e", b"source", compile_result,
            mode=E2EMode.REFERENCE,
            backend_name="scripted-reference",
            backend_revision="1",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = write_e2e_preflight_bundle(temp, preflight, compile_result)
            (root / "runtime-smoke.json").write_text(json.dumps(smoke()), encoding="utf-8")
            first = finalize_e2e_bundle(root)
            bytes_a = (root / "e2e-report.json").read_bytes()
            second = finalize_e2e_bundle(root)
            bytes_b = (root / "e2e-report.json").read_bytes()
            self.assertEqual(first, second)
            self.assertEqual(bytes_a, bytes_b)


if __name__ == "__main__":
    unittest.main()
