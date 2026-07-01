import hashlib
import json
from pathlib import Path

from src.model_builder.config_provenance import config_differences, materialize_version_configs
from src.model_builder.hf_config import ConfigMappingEntry
from src.model_builder.registry import ResolvedVersion


def version() -> ResolvedVersion:
    return ResolvedVersion(
        family_id="tiny", family_name="Tiny", category="Text models", version_id="tiny",
        display_name="Tiny", library="transformers", architecture_key="tiny",
        config_class="TinyConfig", entrypoint_module="example", entrypoint_class="TinyModel",
        task_type="text", structure_key="sha256.tiny",
    )


def entry() -> ConfigMappingEntry:
    revision = "a" * 40
    return ConfigMappingEntry(
        version_id="tiny", repo_id="publisher/tiny", config_path="config.json", revision=revision,
        pinned_url=f"https://huggingface.co/publisher/tiny/blob/{revision}/config.json",
        publisher="Publisher", license="apache-2.0", mapping_status="approved", review_notes="test",
    )


def test_config_differences_distinguishes_missing_and_changed_values() -> None:
    assert config_differences(
        {"same": 1, "changed": 2, "official": None},
        {"same": 1, "changed": 3, "trace": None},
    ) == [
        {"path": "changed", "status": "changed", "official_value": 2, "trace_value": 3},
        {"path": "official", "status": "official_only", "official_value": None},
        {"path": "trace", "status": "trace_only", "trace_value": None},
    ]


def test_materialize_keeps_raw_official_config_and_derivation(tmp_path: Path) -> None:
    raw = b'{\n  "model_type": "tiny",\n  "hidden_size": 2048\n}\n'
    source = tmp_path / "official/tiny"
    source.mkdir(parents=True)
    (source / "config.json").write_bytes(raw)
    (source / "metadata.json").write_text(json.dumps({
        "revision": "a" * 40,
        "repo_id": "publisher/tiny",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }), encoding="utf-8")

    result = materialize_version_configs(
        tmp_path / "out", version(), {"model_type": "tiny", "hidden_size": 16}, entry(), tmp_path / "official",
    )

    assert result["status"] == "passed"
    assert (tmp_path / "out/configs/official/tiny.json").read_bytes() == raw
    trace = json.loads((tmp_path / "out/configs/trace/tiny.json").read_text(encoding="utf-8"))
    assert trace["config"]["hidden_size"] == 16
    assert trace["derivation"]["overrides"][0]["path"] == "hidden_size"


def test_missing_official_config_marks_only_version_partial(tmp_path: Path) -> None:
    result = materialize_version_configs(
        tmp_path / "out", version(), {"model_type": "tiny"}, entry(), tmp_path / "official",
    )
    assert result["status"] == "partial"
    assert result["warnings"][0]["code"] == "official_config_unavailable"
    assert result["official_config_ref"] is None
