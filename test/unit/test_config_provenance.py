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


def test_missing_mapping_records_a_specific_warning(tmp_path: Path) -> None:
    result = materialize_version_configs(
        tmp_path / "out", version(), {"model_type": "tiny"}, None, tmp_path / "official",
    )
    assert result["status"] == "partial"
    assert result["warnings"][0]["code"] == "official_config_mapping_missing"


def test_native_mamba2_config_uses_the_compatibility_adapter(tmp_path: Path) -> None:
    raw = b'{"ssm_cfg":{"layer":"Mamba2"}}\n'
    source = tmp_path / "official/tiny"
    source.mkdir(parents=True)
    (source / "config.json").write_bytes(raw)
    (source / "metadata.json").write_text(json.dumps({
        "revision": "a" * 40,
        "repo_id": "publisher/tiny",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }), encoding="utf-8")
    mamba = ResolvedVersion(**{**version().as_dict(), "architecture_key": "mamba2"})

    result = materialize_version_configs(
        tmp_path / "out", mamba, {"model_type": "mamba2"}, entry(), tmp_path / "official",
    )
    assert result["status"] == "passed"
    assert result["official_config_source"]["compatibility_adapter"] == "native-mamba2-v1"


def test_pinned_config_rejects_each_metadata_or_compatibility_mismatch(tmp_path: Path) -> None:
    raw = b'{"model_type":"tiny"}\n'
    mutations = (
        {"revision": "b" * 40},
        {"sha256": "0" * 64},
        {"repo_id": "another/repository"},
        {"config": b'{"model_type":"other"}\n'},
    )
    for index, mutation in enumerate(mutations):
        case = tmp_path / str(index)
        source = case / "official/tiny"
        source.mkdir(parents=True)
        case_raw = mutation.get("config", raw)
        (source / "config.json").write_bytes(case_raw)
        metadata = {
            "revision": "a" * 40,
            "repo_id": "publisher/tiny",
            "sha256": hashlib.sha256(case_raw).hexdigest(),
            **{key: value for key, value in mutation.items() if key != "config"},
        }
        (source / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        result = materialize_version_configs(
            case / "out", version(), {"model_type": "tiny"}, entry(), case / "official",
        )
        assert result["status"] == "partial"
        assert result["warnings"][0]["code"] == "official_config_unavailable"
