import json
from pathlib import Path

import torch
from torch import nn

from src.model_builder import builder
from src.model_builder.factory import ModelBundle
from src.model_builder.registry import ResolvedVersion


class TinyModel(nn.Module):
    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return value + 1


def test_include_filter_accepts_normalized_version_ids(monkeypatch, tmp_path: Path) -> None:
    catalog = tmp_path / "models.txt"
    catalog.write_text("Data2Vec\n", encoding="utf-8")
    versions = tuple(
        ResolvedVersion(
            family_id="data2vec",
            family_name="Data2Vec",
            category="Multimodal models",
            version_id=f"data2vec-{index}",
            display_name=f"Data2Vec {index}",
            library="transformers",
            architecture_key=f"data2vec-{index}",
            config_class="Data2VecConfig",
            entrypoint_module="example",
            entrypoint_class="Data2VecModel",
            task_type="multimodal",
            structure_key=f"sha256.{index}",
        )
        for index in range(1, 4)
    )
    monkeypatch.setattr(builder, "resolve_catalog", lambda entries: versions)

    report = builder.build(
        catalog,
        tmp_path / "scope.yaml",
        tmp_path / "model_code",
        tmp_path / "cache",
        plan_only=True,
        includes=("data2vec-3",),
    )

    assert report["selected_version_count"] == 1


def test_aliases_execute_one_canonical_inference(monkeypatch, tmp_path: Path) -> None:
    catalog = tmp_path / "models.txt"
    catalog.write_text("BERT\nBertJapanese\n", encoding="utf-8")
    create_calls = []

    def create(version):
        create_calls.append(version.version_id)
        return ModelBundle(TinyModel(), (torch.zeros(1, 4),), {}, {"hidden_size": 4})

    monkeypatch.setattr(builder, "create_model", create)
    monkeypatch.setattr(builder, "_write_licenses", lambda root, out, packages: None)
    report = builder.build(
        catalog,
        tmp_path / "scope.yaml",
        tmp_path / "model_code",
        tmp_path / "cache",
        resume=False,
    )

    assert report["status"] == "passed"
    assert report["selected_version_count"] == 2
    assert report["passed_version_count"] == 2
    assert len(report["executions"]) == 1
    assert create_calls == ["bert"]
    manifest = json.loads((tmp_path / "model_code" / "manifest.v2.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2.1.0"
    source_assets = list((tmp_path / "model_code" / "sources").glob("source.*.json"))
    assert source_assets
    source = json.loads(source_assets[0].read_text(encoding="utf-8"))
    assert source["redistributed"] is True
    assert (tmp_path / "model_code" / source["asset_path"]).is_file()

    second = builder.build(
        catalog,
        tmp_path / "second-scope.yaml",
        tmp_path / "second-model-code",
        tmp_path / "cache",
        resume=True,
    )

    assert second["status"] == "passed"
    assert second["executions"] == []
    assert second["passed_version_count"] == 2
    assert create_calls == ["bert"]
    assert (tmp_path / "second-model-code" / "traces" / f"{next(iter(report['executions']))}.json").is_file()
