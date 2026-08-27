from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


PINNED_SEE_THROUGH_REVISION = "7f139bb25c46a0c8ac720d95ddab185fcda5451c"


def _check(code: str, passed: bool, message: str, **details: Any) -> dict[str, object]:
    return {
        "code": code,
        "passed": bool(passed),
        "message": message,
        **({"details": details} if details else {}),
    }


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _provider_factory(spec: str) -> tuple[bool, str]:
    if ":" not in spec:
        return False, "factory must use module:attribute syntax"
    module_name, attribute = spec.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute)
    except Exception as exc:  # pragma: no cover - depends on runner environment
        return False, f"factory import failed: {type(exc).__name__}: {exc}"
    if not callable(factory):
        return False, "resolved factory is not callable"
    try:
        provider = factory()
    except Exception as exc:  # pragma: no cover - depends on runner environment
        return False, f"factory invocation failed: {type(exc).__name__}: {exc}"
    name = getattr(provider, "provider_name", None)
    revision = getattr(provider, "provider_revision", None)
    if not isinstance(name, str) or not name or not isinstance(revision, str) or not revision:
        return False, "provider must expose non-empty provider_name/provider_revision"
    return True, f"{name}@{revision}"


def build_report(args: argparse.Namespace) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    root = Path(args.see_through_root).expanduser().resolve()
    image = Path(args.input).expanduser().resolve()

    checks.append(_check(
        "python-version",
        sys.version_info >= (3, 11),
        f"Python {sys.version.split()[0]}",
    ))

    nvidia_smi = shutil.which("nvidia-smi")
    checks.append(_check(
        "nvidia-smi-present",
        nvidia_smi is not None,
        nvidia_smi or "nvidia-smi not found",
    ))

    gpu_rows: list[dict[str, object]] = []
    if nvidia_smi is not None:
        proc = _run([
            nvidia_smi,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ])
        if proc.returncode == 0:
            for raw in proc.stdout.splitlines():
                fields = [part.strip() for part in raw.split(",")]
                if len(fields) < 3:
                    continue
                try:
                    memory_mib = int(float(fields[1]))
                except ValueError:
                    memory_mib = 0
                gpu_rows.append({
                    "name": fields[0],
                    "memoryMiB": memory_mib,
                    "driver": fields[2],
                })
        checks.append(_check(
            "nvidia-smi-query",
            proc.returncode == 0 and bool(gpu_rows),
            proc.stderr.strip() or f"detected {len(gpu_rows)} NVIDIA GPU(s)",
            gpus=gpu_rows,
        ))

    min_vram = args.min_vram_mib
    max_vram = max((int(item["memoryMiB"]) for item in gpu_rows), default=0)
    checks.append(_check(
        "gpu-vram",
        max_vram >= min_vram,
        f"max VRAM {max_vram} MiB; required >= {min_vram} MiB",
        groupOffload=bool(args.group_offload),
    ))

    try:
        import torch  # type: ignore
        cuda_available = bool(torch.cuda.is_available())
        torch_message = (
            f"torch={getattr(torch, '__version__', 'unknown')} "
            f"cuda={getattr(torch.version, 'cuda', None)} "
            f"available={cuda_available}"
        )
    except Exception as exc:  # pragma: no cover - runner dependency
        cuda_available = False
        torch_message = f"torch import failed: {type(exc).__name__}: {exc}"
    checks.append(_check("torch-cuda", cuda_available, torch_message))

    script = root / "inference" / "scripts" / "inference_psd.py"
    checks.append(_check(
        "see-through-script",
        script.is_file(),
        str(script),
    ))
    checks.append(_check(
        "source-image",
        image.is_file() and image.stat().st_size > 0,
        str(image),
    ))

    git_proc = _run(["git", "rev-parse", "HEAD"], cwd=root) if root.is_dir() else None
    revision = git_proc.stdout.strip() if git_proc and git_proc.returncode == 0 else ""
    pinned_ok = bool(revision) and (args.allow_unpinned or revision == PINNED_SEE_THROUGH_REVISION)
    checks.append(_check(
        "see-through-revision",
        pinned_ok,
        f"revision={revision or 'unknown'} expected={PINNED_SEE_THROUGH_REVISION}",
        allowUnpinned=bool(args.allow_unpinned),
    ))

    completion_ok, completion_message = _provider_factory(args.completion_provider_factory)
    checks.append(_check(
        "completion-provider",
        completion_ok,
        completion_message,
    ))
    landmark_ok, landmark_message = _provider_factory(args.landmark_provider_factory)
    checks.append(_check(
        "landmark-provider",
        landmark_ok,
        landmark_message,
    ))

    passed = all(bool(item["passed"]) for item in checks)
    return {
        "version": 1,
        "passed": passed,
        "seeThroughRoot": str(root),
        "input": str(image),
        "groupOffload": bool(args.group_offload),
        "minimumVramMiB": min_vram,
        "pinnedSeeThroughRevision": PINNED_SEE_THROUGH_REVISION,
        "checks": checks,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="a2d-production-gpu-preflight")
    p.add_argument("--see-through-root", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--completion-provider-factory", required=True)
    p.add_argument("--landmark-provider-factory", required=True)
    p.add_argument("--group-offload", action="store_true")
    p.add_argument("--min-vram-mib", type=int)
    p.add_argument("--allow-unpinned", action="store_true")
    p.add_argument("--json-out")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.min_vram_mib is None:
        args.min_vram_mib = 10_000 if args.group_offload else 12_000
    if args.min_vram_mib < 1:
        raise SystemExit("--min-vram-mib must be positive")
    report = build_report(args)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
