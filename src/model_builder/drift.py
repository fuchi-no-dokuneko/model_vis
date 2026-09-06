from __future__ import annotations

import argparse
import json
import multiprocessing
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .semantics import materialize_catalog
from .util import read_json
from .validate import validate


def managed_paths(model_code: Path) -> list[Path]:
    manifest = read_json(model_code / "manifest.v2.json")
    paths = {
        Path("manifest.v2.json"),
        Path(manifest["asset_index"]),
        Path(manifest["build_report"]),
        Path("indexes/semantic.v1.json"),
        Path("indexes/semantic-report.v1.json"),
        Path("contracts/interface-tags.v1.json"),
        Path("contracts/semantic-model.schema.json"),
    }
    paths.update(Path("versions") / f"{version_id}.json" for version_id in manifest["versions"])
    paths.update(Path("semantics") / f"{version_id}.json" for version_id in manifest["versions"])
    return sorted(paths)


def parsed_snapshot(model_code: Path) -> dict[str, Any]:
    return {
        path.as_posix(): read_json(model_code / path)
        for path in managed_paths(model_code)
    }


def differences(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    names = sorted(set(left) | set(right))
    return [name for name in names if left.get(name) != right.get(name)]


def regenerate_copy(
    model_code: Path, destination: Path, catalog: Path, cloudflare_target: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    shutil.copytree(model_code, destination)
    materialize_catalog(destination)
    snapshot = parsed_snapshot(destination)
    validation = validate(destination, catalog, cloudflare_target, allow_partial=True)
    return snapshot, validation


def check_generated_drift(
    model_code: Path,
    catalog: Path,
    *,
    cloudflare_target: str = "free",
) -> dict[str, Any]:
    checked_in = parsed_snapshot(model_code)
    with tempfile.TemporaryDirectory(prefix="model-vis-drift-") as temporary:
        temporary_root = Path(temporary)
        first = temporary_root / "first"
        second = temporary_root / "second"
        # Each generation and its complete validation run in a fresh process.
        # The two independent copies can use both cores of the existing runner
        # without relaxing the drift or validation gates as the catalog grows.
        with ProcessPoolExecutor(
            max_workers=2, mp_context=multiprocessing.get_context("spawn"),
        ) as workers:
            jobs = [
                workers.submit(regenerate_copy, model_code, path, catalog, cloudflare_target)
                for path in (first, second)
            ]
            (first_snapshot, first_validation), (second_snapshot, second_validation) = [
                job.result() for job in jobs
            ]
        reproducibility_drift = differences(first_snapshot, second_snapshot)
        checked_in_drift = differences(checked_in, first_snapshot)
        validations = [first_validation, second_validation]

    errors = [
        error
        for validation in validations
        for error in validation["errors"]
    ]
    passed = not reproducibility_drift and not checked_in_drift and not errors
    return {
        "passed": passed,
        "managed_file_count": len(checked_in),
        "reproducibility_drift": reproducibility_drift,
        "checked_in_drift": checked_in_drift,
        "validation_errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check deterministic generated catalog drift")
    parser.add_argument("--model-code", type=Path, default=Path("model_code"))
    parser.add_argument("--catalog", type=Path, default=Path("model.txt"))
    parser.add_argument("--cloudflare-target", choices=("free", "paid"), default="free")
    args = parser.parse_args()
    result = check_generated_drift(
        args.model_code,
        args.catalog,
        cloudflare_target=args.cloudflare_target,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
