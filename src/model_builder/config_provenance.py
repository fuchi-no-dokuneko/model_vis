from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .hf_config import ConfigMappingEntry, parse_config
from .registry import ResolvedVersion
from .util import read_json, write_json


MISSING = object()


def config_differences(official: Any, trace: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(official, dict) and isinstance(trace, dict):
        differences: list[dict[str, Any]] = []
        for key in sorted(set(official) | set(trace)):
            child = f"{path}.{key}" if path else key
            differences.extend(config_differences(
                official.get(key, MISSING), trace.get(key, MISSING), child,
            ))
        return differences
    if official is not MISSING and trace is not MISSING and official == trace:
        return []
    if official is MISSING:
        return [{"path": path, "status": "trace_only", "trace_value": trace}]
    if trace is MISSING:
        return [{"path": path, "status": "official_only", "official_value": official}]
    return [{
        "path": path,
        "status": "changed",
        "official_value": official,
        "trace_value": trace,
    }]


def _normalized_model_type(value: str | None) -> str:
    return (value or "").lower().replace("-", "_")


def _compatible(version: ResolvedVersion, config: dict[str, Any]) -> tuple[bool, str | None]:
    expected = _normalized_model_type(version.architecture_key)
    actual = _normalized_model_type(config.get("model_type"))
    if expected == "mamba2" and not actual and config.get("ssm_cfg", {}).get("layer") == "Mamba2":
        return True, "native-mamba2-v1"
    return expected == actual, None


def _warning(code: str, message: str) -> dict[str, str]:
    return {"severity": "warning", "code": code, "message": message}


def materialize_version_configs(
    out: Path,
    version: ResolvedVersion,
    trace_config: dict[str, Any],
    entry: ConfigMappingEntry | None,
    official_root: Path,
) -> dict[str, Any]:
    trace_ref = f"configs/trace/{version.version_id}.json"
    official_ref = f"configs/official/{version.version_id}.json"
    diff_ref = f"configs/diffs/{version.version_id}.json"
    warnings: list[dict[str, str]] = []
    official: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    adapter: str | None = None

    if entry is None:
        warnings.append(_warning(
            "official_config_mapping_missing",
            f"No pinned official config mapping exists for {version.version_id}.",
        ))
    else:
        config_path = official_root / version.version_id / "config.json"
        metadata_path = official_root / version.version_id / "metadata.json"
        try:
            raw = config_path.read_bytes()
            metadata = read_json(metadata_path)
            digest = hashlib.sha256(raw).hexdigest()
            if metadata.get("revision") != entry.revision:
                raise ValueError("local metadata revision does not match mapping")
            if metadata.get("sha256") != digest:
                raise ValueError("local config hash does not match prefetch metadata")
            if metadata.get("repo_id") != entry.repo_id:
                raise ValueError("local metadata repository does not match mapping")
            official = parse_config(raw)
            compatible, adapter = _compatible(version, official)
            if not compatible:
                raise ValueError(
                    f"official model_type {official.get('model_type')!r} does not match "
                    f"trace architecture {version.architecture_key!r}"
                )
            destination = out / official_ref
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            source = {
                "repo_id": entry.repo_id,
                "config_path": entry.config_path,
                "revision": entry.revision,
                "pinned_url": entry.pinned_url,
                "sha256": digest,
                "size_bytes": len(raw),
                "publisher": entry.publisher,
                "license": entry.license,
                "mapping_status": entry.mapping_status,
                "review_notes": entry.review_notes,
                "compatibility_adapter": adapter,
            }
        except (OSError, ValueError) as exc:
            warnings.append(_warning(
                "official_config_unavailable",
                f"Pinned official config is unavailable or incompatible: {exc}",
            ))

    differences = config_differences(official, trace_config) if official is not None else []
    write_json(out / trace_ref, {
        "schema_version": "1.0.0",
        "kind": "trace_config",
        "version_id": version.version_id,
        "config": trace_config,
        "derivation": {
            "strategy": "deterministic-compact-cpu-trace",
            "official_config_available": official is not None,
            "compatibility_adapter": adapter,
            "overrides": differences,
        },
    })
    refs = [trace_ref]
    result: dict[str, Any] = {
        "status": "partial" if warnings else "passed",
        "warnings": warnings,
        "trace_config_ref": trace_ref,
        "official_config_ref": official_ref if official is not None else None,
        "config_diff_ref": diff_ref if official is not None else None,
        "official_config_source": source,
        "artifact_refs": refs,
    }
    if official is not None:
        write_json(out / diff_ref, {
            "schema_version": "1.0.0",
            "version_id": version.version_id,
            "official_config_ref": official_ref,
            "trace_config_ref": trace_ref,
            "difference_count": len(differences),
            "differences": differences,
        })
        refs.extend((official_ref, diff_ref))
    return result
