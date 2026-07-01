import json
from pathlib import Path
from urllib.error import URLError

import pytest

from src.model_builder import hf_config


def mapping_entry(**overrides):
    revision = "a" * 40
    values = {
        "version_id": "tiny",
        "repo_id": "publisher/tiny",
        "config_path": "config.json",
        "revision": revision,
        "pinned_url": f"https://huggingface.co/publisher/tiny/blob/{revision}/config.json",
        "publisher": "Publisher",
        "license": "apache-2.0",
        "mapping_status": "approved",
        "review_notes": "test",
    }
    values.update(overrides)
    return values


def write_mapping(path: Path, entry: dict) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.0.0",
        "mapping_version": "test.1",
        "entries": [entry],
    }), encoding="utf-8")


def test_mapping_requires_full_sha_and_safe_config_path(tmp_path: Path) -> None:
    path = tmp_path / "mapping.json"
    write_mapping(path, mapping_entry(revision="main"))
    with pytest.raises(ValueError, match="full lowercase commit SHA"):
        hf_config.load_mapping(path)

    write_mapping(path, mapping_entry(config_path="../config.json"))
    with pytest.raises(ValueError, match="safely identify"):
        hf_config.load_mapping(path)


def test_parse_config_rejects_non_objects_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        hf_config.parse_config(b"[]")
    with pytest.raises(ValueError, match="non-finite"):
        hf_config.parse_config(b'{"value": NaN}')


def test_prefetch_writes_only_config_and_local_metadata(monkeypatch, tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.json"
    write_mapping(mapping, mapping_entry())
    body = b'{"model_type":"tiny","hidden_size":32}\n'
    monkeypatch.setattr(hf_config, "fetch_config", lambda entry: (body, entry.download_url))

    report = hf_config.prefetch(mapping, tmp_path / "official")

    assert report["status"] == "passed"
    assert (tmp_path / "official/tiny/config.json").read_bytes() == body
    metadata = json.loads((tmp_path / "official/tiny/metadata.json").read_text(encoding="utf-8"))
    assert metadata["revision"] == "a" * 40
    assert sorted(path.name for path in (tmp_path / "official/tiny").iterdir()) == ["config.json", "metadata.json"]


def test_prefetch_records_one_model_failure_without_erasing_others(monkeypatch, tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.json"
    document = {
        "schema_version": "1.0.0",
        "mapping_version": "test.1",
        "entries": [mapping_entry(), mapping_entry(
            version_id="broken",
            repo_id="publisher/broken",
            pinned_url=f"https://huggingface.co/publisher/broken/blob/{'a' * 40}/config.json",
        )],
    }
    mapping.write_text(json.dumps(document), encoding="utf-8")

    def fetch(entry):
        if entry.version_id == "broken":
            raise URLError("missing")
        return b'{"model_type":"tiny"}', entry.download_url

    monkeypatch.setattr(hf_config, "fetch_config", fetch)
    report = hf_config.prefetch(mapping, tmp_path / "official")

    assert report["status"] == "partial"
    assert report["fetched"][0]["version_id"] == "tiny"
    assert report["failures"][0]["version_id"] == "broken"
