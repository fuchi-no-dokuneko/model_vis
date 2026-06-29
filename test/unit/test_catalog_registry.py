from pathlib import Path

from src.model_builder.catalog import read_catalog
from src.model_builder.registry import resolve_catalog, resolve_entry


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

