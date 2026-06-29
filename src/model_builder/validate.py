from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .catalog import read_catalog
from .guard import scan_forbidden_artifacts
from .util import read_json


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _schema_name(relative: Path) -> str | None:
    value = relative.as_posix()
    if value == "manifest.v1.json":
        return "manifest.v1.schema.json"
    if value.startswith("families/"):
        return "family.v1.schema.json"
    if value.startswith("versions/"):
        return "version.v1.schema.json"
    if value.startswith("traces/"):
        return "trace.v1.schema.json"
    if value.startswith("graphs/"):
        return "graph.v1.schema.json"
    if value.startswith("blocks/"):
        return "blocks.v1.schema.json"
    if value.startswith("configs/"):
        return "config.v1.schema.json"
    if value.startswith("sources/"):
        return "source.v1.schema.json"
    return {
        "indexes/search.v1.json": "search-index.v1.schema.json",
        "indexes/assets.v1.json": "asset-index.v1.schema.json",
        "indexes/license_manifest.v1.json": "license-index.v1.schema.json",
        "indexes/build_report.v1.json": "build-report.v1.schema.json",
    }.get(value)


def validate(
    model_code: Path,
    catalog_path: Path,
    cloudflare_target: str = "free",
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = model_code / "manifest.v1.json"
    if not manifest_path.is_file():
        return {"passed": False, "errors": [f"missing {manifest_path}"]}
    manifest = read_json(manifest_path)
    catalog = read_catalog(catalog_path)
    report = read_json(model_code / manifest["build_report"])
    for path in model_code.rglob("*.json"):
        relative = path.relative_to(model_code)
        schema_name = _schema_name(relative)
        if schema_name is None:
            errors.append(f"no schema is assigned to {relative}")
            continue
        try:
            instance = read_json(path)
            schema = read_json(SCHEMA_ROOT / schema_name)
            validation_errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda item: list(item.path))
            errors.extend(f"{relative}: {item.message}" for item in validation_errors)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: {exc}")
    expected = {entry.family_id for entry in catalog.entries}
    actual = set(manifest["families"])
    if allow_partial and not actual:
        errors.append("partial build contains no families")
    elif allow_partial and not actual <= expected:
        errors.append(f"partial build has unknown families: {sorted(actual - expected)}")
    elif not allow_partial and expected != actual:
        errors.append(f"family coverage mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    if report["status"] != "passed":
        errors.append(f"build report status is {report['status']!r}")
    for version_id in manifest["versions"]:
        path = model_code / "versions" / f"{version_id}.json"
        if not path.is_file():
            errors.append(f"missing version asset {path}")
            continue
        version = read_json(path)
        if version.get("status") != "passed" or version.get("trace_event_count", 0) <= 0:
            errors.append(f"version did not pass a real trace: {version_id}")
        if not version.get("top_level_outputs"):
            errors.append(f"version has no top-level output summary: {version_id}")
    if report.get("passed_version_count") != len(manifest["versions"]):
        errors.append("manifest version count does not match passed build-report count")
    limits = manifest["cloudflare_pages_check"]
    file_limit = 20_000 if cloudflare_target == "free" else 100_000
    if limits["file_count"] > file_limit or limits["max_file_size_bytes"] > 25 * 1024 * 1024:
        errors.append("Cloudflare Pages asset limits exceeded")
    forbidden = scan_forbidden_artifacts([model_code])
    if forbidden:
        errors.append("forbidden artifacts: " + ", ".join(map(str, forbidden)))
    return {"passed": not errors, "errors": errors, "version_count": len(manifest["versions"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated model assets")
    parser.add_argument("--model-code", type=Path, default=Path("model_code"))
    parser.add_argument("--catalog", type=Path, default=Path("model.txt"))
    parser.add_argument("--scope", type=Path, default=Path("model_scope.generated.yaml"))
    parser.add_argument("--cloudflare-target", choices=("free", "paid"), default="free")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Validate a development subset while retaining strict full-catalog validation by default",
    )
    args = parser.parse_args()
    result = validate(
        args.model_code,
        args.catalog,
        args.cloudflare_target,
        allow_partial=args.allow_partial,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
