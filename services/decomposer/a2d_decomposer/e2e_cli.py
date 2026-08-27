from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

from .bridge import decode_decompose_and_compile
from .e2e import E2EGate, E2EMode, build_e2e_preflight, finalize_e2e_bundle, write_e2e_preflight_bundle
from .production import SEE_THROUGH_V3_REFERENCE_REVISION, SeeThroughConfig, SeeThroughProcessBackend


def _factory(spec: str | None):
    if spec is None:
        return None
    if ":" not in spec:
        raise ValueError("provider factory must use module:attribute syntax")
    module_name, attribute = spec.split(":", 1)
    module = importlib.import_module(module_name)
    value = getattr(module, attribute)
    if not callable(value):
        raise TypeError(f"provider factory {spec} is not callable")
    return value()


def _run(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    payload = source_path.read_bytes()
    config = SeeThroughConfig(
        repo_root=args.see_through_root,
        python_executable=args.python,
        seed=args.seed,
        resolution=args.resolution,
        resolution_depth=args.resolution_depth,
        inference_steps=args.inference_steps,
        inference_steps_depth=args.inference_steps_depth,
        group_offload=args.group_offload,
        backend_revision=args.backend_revision,
        timeout_seconds=args.timeout_seconds,
    )
    backend = SeeThroughProcessBackend(config)
    completion_provider = _factory(args.completion_provider_factory)
    landmark_provider = _factory(args.landmark_provider_factory)
    result = decode_decompose_and_compile(
        args.character_id,
        payload,
        backend,
        completion_provider=completion_provider,
        landmark_provider=landmark_provider,
    )
    preflight = build_e2e_preflight(
        args.character_id,
        payload,
        result,
        mode=E2EMode.PRODUCTION,
        backend_name="see-through",
        backend_revision=config.backend_revision,
        completion_provider=completion_provider,
        landmark_provider=landmark_provider,
    )
    output = write_e2e_preflight_bundle(args.output, preflight, result)
    summary = {
        "output": str(output),
        "decomposerReady": preflight.decomposer_ready,
        "compilerQaReady": preflight.compiler_qa_ready,
        "qualityDecision": preflight.quality_decision,
        "qualityScore": preflight.quality_score,
        "artifactSha256": preflight.artifact_sha256,
        "next": "run the TypeScript runtime smoke and then finalize the E2E report",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if preflight.compiler_present else 2


def _finalize(args: argparse.Namespace) -> int:
    report = finalize_e2e_bundle(args.output)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if report.gate is E2EGate.PASS:
        return 0
    if report.gate is E2EGate.NOT_RUN:
        return 3
    return 4


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="a2d-single-image-e2e")
    sub = root.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the production single-image pipeline")
    run.add_argument("--input", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--character-id", required=True)
    run.add_argument("--see-through-root", required=True)
    run.add_argument("--python", default=sys.executable)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--resolution", type=int, default=1280)
    run.add_argument("--resolution-depth", type=int, default=768)
    run.add_argument("--inference-steps", type=int, default=30)
    run.add_argument("--inference-steps-depth", type=int, default=-1)
    run.add_argument("--group-offload", action="store_true")
    run.add_argument("--timeout-seconds", type=float, default=1800.0)
    run.add_argument("--backend-revision", default=SEE_THROUGH_V3_REFERENCE_REVISION)
    run.add_argument("--completion-provider-factory")
    run.add_argument("--landmark-provider-factory")
    run.set_defaults(handler=_run)

    finalize = sub.add_parser("finalize", help="combine preflight and runtime-smoke evidence")
    finalize.add_argument("--output", required=True)
    finalize.set_defaults(handler=_finalize)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except Exception as exc:
        print(f"a2d-single-image-e2e: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
