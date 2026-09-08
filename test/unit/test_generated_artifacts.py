from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[2]


def run_module(module: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def copy_real_semantic_fixture(destination: Path, version_id: str = "apertus") -> None:
    source = ROOT / "model_code"
    manifest = json.loads((source / "manifest.v2.json").read_text(encoding="utf-8"))
    version = json.loads((source / "versions" / f"{version_id}.json").read_text(encoding="utf-8"))
    destination.mkdir()
    for relative in {
        version["graph_ref"],
        version.get("trace_config_ref"),
        version.get("config_ref"),
        version.get("official_config_ref"),
    } - {None}:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    version_target = destination / "versions" / f"{version_id}.json"
    version_target.parent.mkdir(parents=True)
    shutil.copy2(source / "versions" / f"{version_id}.json", version_target)

    report = {
        "catalog_model_count": 1,
        "normalized_version_count": 1,
        "selected_version_count": 1,
        "failures": [],
    }
    report_target = destination / "indexes" / "build_report.v2.json"
    report_target.parent.mkdir(parents=True)
    report_target.write_text(json.dumps(report), encoding="utf-8")
    (destination / "indexes" / "assets.v2.json").write_text("[]\n", encoding="utf-8")
    search = json.loads((source / manifest["search_index"]).read_text())
    (destination / "indexes" / "search.v2.json").write_text(json.dumps([item for item in search if item["version_id"] == version_id]))
    fixture_manifest = {
        "schema_version": manifest["schema_version"],
        "generated_at": manifest["generated_at"],
        "semantic_generated_at": manifest["semantic_generated_at"],
        "families": [version["family_id"]],
        "versions": [version_id],
        "asset_index": "indexes/assets.v2.json",
        "build_report": "indexes/build_report.v2.json",
        "search_index": "indexes/search.v2.json",
    }
    (destination / "manifest.v2.json").write_text(
        json.dumps(fixture_manifest),
        encoding="utf-8",
    )


def semantic_snapshot(model_code: Path) -> dict[str, object]:
    return {
        relative: json.loads((model_code / relative).read_text(encoding="utf-8"))
        for relative in (
            "manifest.v2.json",
            "indexes/semantic.v1.json",
            "indexes/semantic-report.v1.json",
            "semantics/apertus.json",
            "contracts/interface-tags.v1.json",
            "contracts/semantic-model.schema.json",
        )
    }


def test_real_catalog_plan_cli_is_deterministic(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.txt"
    catalog.write_text("BERT\nApertus\n", encoding="utf-8")
    outputs = []
    for name in ("first.yaml", "second.yaml"):
        scope = tmp_path / name
        result = run_module(
            "src.model_builder",
            "--catalog",
            str(catalog),
            "--scope-out",
            str(scope),
            "--plan-only",
        )
        assert result.returncode == 0, result.stderr
        outputs.append(scope.read_text(encoding="utf-8"))
    assert outputs[0] == outputs[1]


def test_all_maintained_schemas_and_real_generated_fixture_validate(tmp_path: Path) -> None:
    schema_paths = sorted((ROOT / "src" / "schemas").glob("*.schema.json"))
    assert schema_paths
    for schema_path in schema_paths:
        Draft202012Validator.check_schema(json.loads(schema_path.read_text(encoding="utf-8")))

    fixture = tmp_path / "catalog"
    copy_real_semantic_fixture(fixture)
    result = run_module("src.model_builder.semantics", "--model-code", str(fixture))
    assert result.returncode == 0, result.stderr
    schema = json.loads((fixture / "contracts" / "semantic-model.schema.json").read_text(encoding="utf-8"))
    semantic = json.loads((fixture / "semantics" / "apertus.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(semantic)
    assert semantic["version_id"] == "apertus"
    assert semantic["entities"]
    assert semantic["coverage"]
    assert all(0 <= value <= 1 for value in semantic["coverage"].values())


def test_two_real_semantic_cli_generations_are_semantically_identical(tmp_path: Path) -> None:
    fixtures = [tmp_path / "first", tmp_path / "second"]
    for fixture in fixtures:
        copy_real_semantic_fixture(fixture)
        result = run_module("src.model_builder.semantics", "--model-code", str(fixture))
        assert result.returncode == 0, result.stderr
    assert semantic_snapshot(fixtures[0]) == semantic_snapshot(fixtures[1])


def test_semantic_cli_rejects_malformed_manifest(tmp_path: Path) -> None:
    fixture = tmp_path / "malformed"
    fixture.mkdir()
    (fixture / "manifest.v2.json").write_text("{not-json", encoding="utf-8")
    result = run_module("src.model_builder.semantics", "--model-code", str(fixture))
    assert result.returncode != 0
    assert "JSONDecodeError" in result.stderr
