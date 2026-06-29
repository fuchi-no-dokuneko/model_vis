from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .util import slug


SECTION_HEADINGS = {
    "Vision models",
    "Audio models",
    "Video models",
    "Multimodal models",
    "Reinforcement learning models",
    "UNets",
    "VAEs",
}


@dataclass(frozen=True)
class CatalogEntry:
    line_number: int
    display_name: str
    family_id: str
    category: str


@dataclass(frozen=True)
class Catalog:
    entries: tuple[CatalogEntry, ...]
    declarations: tuple[dict[str, object], ...]


def read_catalog(path: Path) -> Catalog:
    if not path.is_file():
        raise FileNotFoundError(f"catalog does not exist: {path}")

    entries: list[CatalogEntry] = []
    declarations: list[dict[str, object]] = []
    category = "Text models"
    seen: set[str] = set()

    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        if name in SECTION_HEADINGS:
            category = name
            declarations.append({"line": line_number, "name": name, "kind": "section"})
            continue

        family_id = slug(name)
        if family_id in seen:
            raise ValueError(f"duplicate catalog family id {family_id!r} on line {line_number}")
        seen.add(family_id)
        entry = CatalogEntry(line_number, name, family_id, category)
        entries.append(entry)
        declarations.append({"line": line_number, "name": name, "kind": "model"})

    if not entries:
        raise ValueError(f"catalog contains no model entries: {path}")
    return Catalog(tuple(entries), tuple(declarations))

