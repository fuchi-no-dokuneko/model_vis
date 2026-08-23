from pathlib import Path

import pytest

from src.model_builder.catalog import CatalogEntry, read_catalog
from src.model_builder.registry import ResolvedVersion, _transformer_version, resolve_catalog, resolve_entry


ROOT = Path(__file__).parents[2]


def test_complete_catalog_resolves() -> None:
    catalog = read_catalog(ROOT / "model.txt")
    versions = resolve_catalog(catalog.entries)

    assert len(catalog.declarations) == 570
    assert len(catalog.entries) == 563
    assert len(versions) == 567
    assert {version.family_id for version in versions} == {entry.family_id for entry in catalog.entries}


def test_aliases_share_canonical_structure() -> None:
    catalog = read_catalog(ROOT / "model.txt")
    by_name = {entry.display_name: entry for entry in catalog.entries}

    bert = resolve_entry(by_name["BERT"])[0]
    japanese = resolve_entry(by_name["BertJapanese"])[0]
    llama = resolve_entry(by_name["LLaMA"])[0]
    llama3 = resolve_entry(by_name["Llama3"])[0]

    assert bert.structure_key == japanese.structure_key
    assert llama.structure_key == llama3.structure_key


def test_catalog_rejects_missing_empty_and_duplicate_inputs(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_catalog(tmp_path / "missing.txt")
    empty = tmp_path / "empty.txt"
    empty.write_text("# comment\n\nVision models\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no model entries"):
        read_catalog(empty)
    duplicate = tmp_path / "duplicate.txt"
    duplicate.write_text("Vision models\nTiny Model\nTiny-Model\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate catalog family"):
        read_catalog(duplicate)


def test_registry_reports_unavailable_transformer_and_diffusers_targets() -> None:
    transformer = CatalogEntry(4, "Missing Transformer", "missing-transformer", "Text models")
    with pytest.raises(KeyError, match="config key"):
        _transformer_version(transformer, "definitely_missing", 0)

    unavailable = CatalogEntry(8, "DefinitelyMissingDiffuser", "missing-diffuser", "UNets")
    with pytest.raises(ValueError, match="line 8"):
        resolve_catalog([unavailable])


def test_resolved_version_serializes_all_fields() -> None:
    value = ResolvedVersion(
        family_id="tiny", family_name="Tiny", category="Text models", version_id="tiny",
        display_name="Tiny", library="transformers", architecture_key="tiny",
        config_class="TinyConfig", entrypoint_module="example", entrypoint_class="TinyModel",
        task_type="text", structure_key="sha256.tiny",
    )
    assert value.as_dict()["entrypoint_class"] == "TinyModel"
