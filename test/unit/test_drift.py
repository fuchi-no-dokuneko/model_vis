import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.model_builder import drift


@pytest.mark.parametrize("problem", [None, "checked_in", "second_generation", "second_validation"])
def test_independent_copies_preserve_both_drift_and_validation_gates(tmp_path, monkeypatch, problem):
    source = tmp_path / "catalog"
    source.mkdir()
    manifest = {"versions": ["test"], "asset_index": "indexes/assets.json", "build_report": "indexes/report.json", "search_index": "indexes/search.json"}
    (source / "manifest.v2.json").write_text(json.dumps(manifest))
    for path in drift.managed_paths(source):
        if path.name != "manifest.v2.json":
            (source / path).parent.mkdir(parents=True, exist_ok=True)
            (source / path).write_text('{"value": 1}')
    before = drift.parsed_snapshot(source)
    validated = set()

    def generate(destination):
        assert destination != source
        if problem == "checked_in" or (problem == "second_generation" and destination.name == "second"):
            (destination / "semantics/test.json").write_text('{"value": 2}')

    def validate(destination, catalog, target, *, allow_partial):
        assert allow_partial and target == "free"
        validated.add(destination.name)
        errors = ["invalid second copy"] if problem == "second_validation" and destination.name == "second" else []
        return {"passed": not errors, "errors": errors}

    # Exercise the same isolated-directory work with deterministic mutations;
    # the full catalog CLI check separately exercises fresh spawned processes.
    monkeypatch.setattr(drift, "ProcessPoolExecutor", lambda **kwargs: ThreadPoolExecutor(max_workers=2))
    monkeypatch.setattr(drift, "materialize_catalog", generate)
    monkeypatch.setattr(drift, "validate", validate)
    result = drift.check_generated_drift(source, tmp_path / "model.txt")
    assert validated == {"first", "second"}
    assert drift.parsed_snapshot(source) == before
    assert result["passed"] == (problem is None)
    assert result["checked_in_drift"] == (["semantics/test.json"] if problem == "checked_in" else [])
    assert result["reproducibility_drift"] == (["semantics/test.json"] if problem == "second_generation" else [])
    assert result["validation_errors"] == (["invalid second copy"] if problem == "second_validation" else [])
