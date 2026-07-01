from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .util import read_json, write_json


MAX_CONFIG_BYTES = 2 * 1024 * 1024
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_HOSTS = {"huggingface.co"}


@dataclass(frozen=True)
class ConfigMappingEntry:
    version_id: str
    repo_id: str
    config_path: str
    revision: str
    pinned_url: str
    publisher: str
    license: str
    mapping_status: str
    review_notes: str

    @property
    def download_url(self) -> str:
        repo = urllib.parse.quote(self.repo_id, safe="/")
        path = urllib.parse.quote(self.config_path, safe="/")
        return f"https://huggingface.co/{repo}/resolve/{self.revision}/{path}"


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def parse_config(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError(f"config exceeds {MAX_CONFIG_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except UnicodeDecodeError as exc:
        raise ValueError("config is not UTF-8") from exc
    if not isinstance(value, dict):
        raise ValueError("config root must be a JSON object")
    return value


def _validate_entry(raw: dict[str, Any]) -> ConfigMappingEntry:
    required = {
        "version_id", "repo_id", "config_path", "revision", "pinned_url",
        "publisher", "license", "mapping_status", "review_notes",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"mapping entry is missing fields: {', '.join(missing)}")
    entry = ConfigMappingEntry(**{key: raw[key] for key in required})
    if not FULL_SHA.fullmatch(entry.revision):
        raise ValueError(f"{entry.version_id}: revision must be a full lowercase commit SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", entry.repo_id):
        raise ValueError(f"{entry.version_id}: invalid Hugging Face repo ID")
    path = PurePosixPath(entry.config_path)
    if path.is_absolute() or ".." in path.parts or path.name != "config.json":
        raise ValueError(f"{entry.version_id}: config_path must safely identify config.json")
    expected = f"https://huggingface.co/{entry.repo_id}/blob/{entry.revision}/{entry.config_path}"
    if entry.pinned_url != expected:
        raise ValueError(f"{entry.version_id}: pinned_url does not match repository, revision, and path")
    return entry


def load_mapping(path: Path) -> tuple[dict[str, Any], dict[str, ConfigMappingEntry]]:
    document = read_json(path)
    if document.get("schema_version") != "1.0.0" or not document.get("mapping_version"):
        raise ValueError("unsupported or missing config mapping version")
    entries: dict[str, ConfigMappingEntry] = {}
    for raw in document.get("entries", []):
        entry = _validate_entry(raw)
        if entry.version_id in entries:
            raise ValueError(f"duplicate mapping for {entry.version_id}")
        entries[entry.version_id] = entry
    if not entries:
        raise ValueError("config mapping contains no entries")
    return document, entries


def _allowed_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and (
        parsed.hostname in ALLOWED_HOSTS or str(parsed.hostname).endswith(".huggingface.co")
    )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not _allowed_url(newurl):
            raise urllib.error.URLError(f"refusing config redirect outside Hugging Face: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_config(entry: ConfigMappingEntry, *, timeout: float = 30) -> tuple[bytes, str]:
    headers = {"Accept": "application/json", "User-Agent": "model-vis-config-prefetch/1.0"}
    if token := os.environ.get("HF_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        entry.download_url,
        headers=headers,
    )
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        if not _allowed_url(final_url):
            raise ValueError(f"config response escaped allowed hosts: {final_url}")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_CONFIG_BYTES:
            raise ValueError(f"config exceeds {MAX_CONFIG_BYTES} bytes")
        raw = response.read(MAX_CONFIG_BYTES + 1)
    parse_config(raw)
    return raw, final_url


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    temporary.replace(path)


def prefetch(mapping_path: Path, out: Path, includes: tuple[str, ...] = ()) -> dict[str, Any]:
    document, entries = load_mapping(mapping_path)
    selected = entries.values()
    if includes:
        wanted = set(includes)
        unknown = sorted(wanted - entries.keys())
        if unknown:
            raise ValueError(f"mapping does not contain requested versions: {', '.join(unknown)}")
        selected = (entries[version_id] for version_id in includes)
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "mapping_version": document["mapping_version"],
        "mapping_path": mapping_path.as_posix(),
        "download_policy": "config-json-only",
        "fetched": [],
        "failures": [],
    }
    for entry in selected:
        try:
            raw, final_url = fetch_config(entry)
            digest = hashlib.sha256(raw).hexdigest()
            destination = out / entry.version_id / "config.json"
            _write_bytes(destination, raw)
            metadata = {
                "schema_version": "1.0.0",
                "version_id": entry.version_id,
                "repo_id": entry.repo_id,
                "config_path": entry.config_path,
                "revision": entry.revision,
                "pinned_url": entry.pinned_url,
                "download_url": entry.download_url,
                "resolved_url": final_url,
                "sha256": digest,
                "size_bytes": len(raw),
                "publisher": entry.publisher,
                "license": entry.license,
                "mapping_status": entry.mapping_status,
                "review_notes": entry.review_notes,
            }
            write_json(out / entry.version_id / "metadata.json", metadata)
            report["fetched"].append({
                "version_id": entry.version_id,
                "sha256": digest,
                "size_bytes": len(raw),
            })
        except (OSError, ValueError, urllib.error.URLError) as exc:
            report["failures"].append({
                "version_id": entry.version_id,
                "error_type": type(exc).__name__,
                "message": str(exc),
            })
    report["status"] = "passed" if not report["failures"] else "partial"
    write_json(out / "prefetch-report.json", report)
    return report


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Download pinned Hugging Face config.json files only")
    command.add_argument("--mapping", type=Path, default=Path("profiles/hf-config-mapping.v1.json"))
    command.add_argument("--out", type=Path, default=Path("official_configs"))
    command.add_argument("--include", action="append", default=[])
    return command


def main() -> int:
    args = parser().parse_args()
    report = prefetch(args.mapping, args.out, tuple(args.include))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
