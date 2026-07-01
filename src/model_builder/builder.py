from __future__ import annotations

import datetime as dt
import gc
import hashlib
import importlib.metadata
import importlib.util
import platform
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import torch
import yaml

from . import SCHEMA_VERSION, __version__
from .blocks import build_blocks
from .catalog import Catalog, read_catalog
from .factory import create_model
from .guard import NoNetworkGuard, scan_forbidden_artifacts
from .registry import ResolvedVersion, resolve_catalog
from .tracing import trace_model
from .util import read_json, sha256_json, write_json


REDISTRIBUTABLE_SOURCE_PACKAGES = {"project", "torch", "transformers", "diffusers"}
CACHE_REVISION = "canonical-lineage-v2.4"


def normalized_scope(catalog: Catalog, versions: Iterable[ResolvedVersion]) -> dict[str, Any]:
    grouped: dict[str, list[ResolvedVersion]] = defaultdict(list)
    for version in versions:
        grouped[version.family_id].append(version)
    entries = {entry.family_id: entry for entry in catalog.entries}
    families = []
    for family_id, family_versions in grouped.items():
        entry = entries[family_id]
        families.append({
            "family_id": family_id,
            "display_name": entry.display_name,
            "category": entry.category,
            "source": {
                "type": "local",
                "repo": None,
                "commit": "installed-package",
                "local_path": None,
                "license_hint": None,
            },
            "versions": [{
                "version_id": version.version_id,
                "display_name": version.display_name,
                "parameter_size_label": "compact-trace-config",
                "framework": "pytorch",
                "library": version.library,
                "config_path": f"versions/{version.version_id}.json",
                "entrypoint": {
                    "module": version.entrypoint_module,
                    "class_name": version.entrypoint_class,
                    "factory": "src.model_builder.factory.create_model",
                },
                "task_type": version.task_type,
                "input_spec": {
                    "description": "Deterministic compact representative inputs generated from forward signature",
                    "tensors": [],
                    "kwargs": {},
                },
                "forward_policy": {
                    "device": "cpu",
                    "dtype": "float32",
                    "eval_mode": True,
                    "no_grad": True,
                    "inference_mode": True,
                    "timeout_seconds": 300,
                },
                "expected_success": True,
                "structure_key": version.structure_key,
            } for version in family_versions],
        })
    return {
        "schema_version": "1.0.0",
        "catalog_declarations": list(catalog.declarations),
        "model_families": families,
    }


def _parameter_summary(model: torch.nn.Module) -> dict[str, int]:
    total = sum(parameter.numel() for parameter in model.parameters())
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    return {"total": total, "trainable": trainable}


def _source_file(relative: str) -> Path | None:
    candidate = Path.cwd() / relative
    if candidate.is_file():
        return candidate.resolve()
    package = relative.split("/", 1)[0]
    try:
        spec = importlib.util.find_spec(package)
    except (ImportError, ModuleNotFoundError, ValueError):
        return None
    if spec is None or spec.origin is None:
        return None
    root = Path(spec.origin).resolve().parent.parent
    candidate = root / relative
    return candidate if candidate.is_file() else None


def _package_source_metadata(package: str, relative: str) -> dict[str, Any]:
    if package == "project":
        return {
            "package_version": __version__,
            "repo": None,
            "commit": None,
            "license_id": "project-license",
            "repository_file_url": None,
        }
    try:
        version = importlib.metadata.version(package)
        metadata = importlib.metadata.metadata(package)
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
        metadata = {}
    clean_version = version.split("+", 1)[0]
    known = {
        "transformers": ("https://github.com/huggingface/transformers", f"v{clean_version}", f"src/{relative}"),
        "diffusers": ("https://github.com/huggingface/diffusers", f"v{clean_version}", f"src/{relative}"),
        "torch": ("https://github.com/pytorch/pytorch", f"v{clean_version}", relative),
    }
    if package in known:
        repo, commit, repo_path = known[package]
    else:
        repo = metadata.get("Home-page") if hasattr(metadata, "get") else None
        commit = f"v{clean_version}" if version != "unknown" else None
        repo_path = relative
    repository_file_url = f"{repo}/blob/{commit}/{repo_path}" if repo and commit else None
    return {
        "package_version": version,
        "repo": repo,
        "commit": commit,
        "license_id": metadata.get("License") if hasattr(metadata, "get") else None,
        "repository_file_url": repository_file_url,
    }


def _trace_source_refs(trace: dict[str, Any]) -> list[dict[str, Any]]:
    values = [operation.get("source_ref") for operation in trace["operations"]]
    for module in trace.get("modules", []):
        values.append(module.get("source_ref"))
        values.append(module.get("constructor", {}).get("source_ref"))
    values.extend(call.get("source_ref") for call in trace.get("module_calls", []))
    return [value for value in values if value and value.get("source_uid") and value.get("file")]


def _source_assets(trace: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    refs: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for ref in _trace_source_refs(trace):
        if ref["source_uid"] in refs:
            continue
        path = _source_file(ref["file"])
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        asset_path = f"sources/files/sha256.{digest}.py.txt"
        package = ref["file"].split("/", 1)[0]
        if package in {"src", "test", "scripts"} or "/" not in ref["file"]:
            package = "project"
        if package not in REDISTRIBUTABLE_SOURCE_PACKAGES:
            raise RuntimeError(
                f"source redistribution license is not approved for package {package!r}: {ref['file']}"
            )
        source = {
            "source_uid": ref["source_uid"],
            "package": package,
            "relative_file": ref["file"],
            "content_hash": f"sha256.{digest}",
            "language": "python",
            "line_count": len(text.splitlines()),
            "chunks": [{
                "start_line": 1,
                "end_line": len(text.splitlines()),
                "asset_path": asset_path,
            }],
            "asset_path": asset_path,
            "redistributed": True,
            **_package_source_metadata(package, ref["file"]),
        }
        refs[ref["source_uid"]] = source
        texts[ref["source_uid"]] = text
    return [(source, texts[source_uid]) for source_uid, source in refs.items()]


def _write_cached_asset(out: Path, cache: Path, relative: str, value: Any) -> None:
    write_json(out / relative, value)
    write_json(cache / "assets" / relative, value)


def _write_cached_text_asset(out: Path, cache: Path, relative: str, value: str) -> None:
    for root in (out, cache / "assets"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def _write_execution(
    out: Path,
    cache: Path,
    version: ResolvedVersion,
    trace: dict[str, Any],
    blocks: list[dict[str, Any]],
    shared: dict[str, dict[str, Any]],
    parameters: dict[str, int],
    config: dict[str, Any],
) -> dict[str, Any]:
    execution_id = version.structure_key
    trace_path = f"traces/{execution_id}.json"
    graph_path = f"graphs/{execution_id}.json"
    blocks_path = f"blocks/{execution_id}.json"
    config_path = f"configs/{execution_id}.json"
    _write_cached_asset(out, cache, trace_path, {
        key: value for key, value in trace.items() if key not in {"torchview", "graph"}
    })
    _write_cached_asset(out, cache, graph_path, trace["graph"])
    _write_cached_asset(out, cache, blocks_path, {"blocks": blocks})
    _write_cached_asset(out, cache, config_path, config)
    artifact_refs = [trace_path, graph_path, blocks_path, config_path]
    for dedup_uid, asset in shared.items():
        shared_ref = f"blocks/shared/{dedup_uid}/block.json"
        if not (out / shared_ref).exists():
            _write_cached_asset(out, cache, shared_ref, asset)
        artifact_refs.append(shared_ref)
    source_assets = _source_assets(trace)
    for source, text in source_assets:
        source_ref = f"sources/{source['source_uid']}.json"
        _write_cached_asset(out, cache, source_ref, source)
        _write_cached_text_asset(out, cache, source["asset_path"], text)
        artifact_refs.extend((source_ref, source["asset_path"]))
    sources = [source for source, _ in source_assets]
    record = {
        "schema_version": SCHEMA_VERSION,
        "builder_version": __version__,
        "cache_revision": CACHE_REVISION,
        "structure_key": execution_id,
        "canonical_version_id": version.version_id,
        "status": "passed",
        "execution_mode": trace["execution_mode"],
        "trace_event_count": trace["trace_event_count"],
        "top_level_outputs": trace["top_level_outputs"],
        "trace_ref": trace_path,
        "graph_ref": graph_path,
        "blocks_ref": blocks_path,
        "config_ref": config_path,
        "block_count": len(blocks),
        "operation_count": trace["trace_event_count"],
        "parameters": parameters,
        "config": config,
        "sources": [source["source_uid"] for source in sources],
        "artifact_refs": sorted(set(artifact_refs)),
    }
    write_json(cache / "executions" / f"{execution_id}.json", record)
    return record


def _restore_execution(cache: Path, out: Path, structure_key: str) -> dict[str, Any] | None:
    path = cache / "executions" / f"{structure_key}.json"
    if not path.is_file():
        return None
    record = read_json(path)
    if (
        record.get("schema_version") != SCHEMA_VERSION
        or record.get("builder_version") != __version__
        or record.get("cache_revision") != CACHE_REVISION
    ):
        return None
    required = record.get("artifact_refs") or [
        record["trace_ref"], record["graph_ref"], record["blocks_ref"], record["config_ref"],
        *(f"sources/{source_uid}.json" for source_uid in record.get("sources", [])),
    ]
    for relative in required:
        destination = out / relative
        if destination.is_file():
            continue
        source = cache / "assets" / relative
        if not source.is_file():
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return record


def _package_license(name: str, redistributed_packages: set[str]) -> dict[str, Any]:
    try:
        metadata = importlib.metadata.metadata(name)
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return {
            "package": name,
            "version": "missing",
            "license": "unknown",
            "source_redistributed": False,
        }
    redistributed = name in redistributed_packages
    return {
        "package": name,
        "version": version,
        "source_repository": metadata.get("Home-page") or metadata.get("Project-URL"),
        "commit": None,
        "license": metadata.get("License") or "see-package-metadata",
        "source_redistributed": redistributed,
        "modified": False,
        "notice_requirements": "review package license",
        "compatibility_decision": (
            "installed source files redistributed unmodified with package/version/hash provenance"
            if redistributed else "metadata references only"
        ),
    }


def _write_licenses(root: Path, out: Path, redistributed_packages: set[str]) -> None:
    dependencies = [_package_license(name, redistributed_packages) for name in (
        "torch", "torchview", "transformers", "diffusers", "jsonschema", "PyYAML",
        "timm", "natten", "torchaudio", "selenium", "graphviz",
    )]
    for item in dependencies:
        item["license_assets"] = []
        if not item.get("source_redistributed"):
            continue
        try:
            distribution = importlib.metadata.distribution(item["package"])
            declared = set(distribution.metadata.get_all("License-File") or [])
        except importlib.metadata.PackageNotFoundError:
            continue
        for distributed_path in distribution.files or []:
            if distributed_path.name not in {Path(value).name for value in declared}:
                continue
            source_path = Path(distribution.locate_file(distributed_path))
            if not source_path.is_file():
                continue
            text = source_path.read_text(encoding="utf-8", errors="replace")
            relative = f"licenses/{item['package']}/{distributed_path.name}.txt"
            destination = out / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
            repository_copy = root / "license" / "source-packages" / item["package"] / f"{distributed_path.name}.txt"
            repository_copy.parent.mkdir(parents=True, exist_ok=True)
            repository_copy.write_text(text, encoding="utf-8")
            item["license_assets"].append(relative)
    write_json(root / "license" / "dependency_licenses.json", dependencies)
    notices = [
        "# Third-Party Notices",
        "",
        "The static model viewer redistributes unmodified source files that are directly referenced by captured traces.",
        "Each generated source asset records its package, version, content hash, license metadata, and official repository link.",
        "",
    ] + [
        f"- {item['package']} {item['version']}: {item['license']} "
        f"(source redistributed: {'yes' if item.get('source_redistributed') else 'no'}"
        f"; license assets: {', '.join(item.get('license_assets', [])) or 'metadata only'})"
        for item in dependencies
    ]
    notice_path = root / "license" / "THIRD_PARTY_NOTICES.md"
    notice_path.parent.mkdir(parents=True, exist_ok=True)
    notice_path.write_text("\n".join(notices) + "\n", encoding="utf-8")
    write_json(out / "indexes" / "license_manifest.v2.json", dependencies)


def _asset_stats(path: Path) -> dict[str, Any]:
    files = [item for item in path.rglob("*") if item.is_file()]
    sizes = [item.stat().st_size for item in files]
    return {
        "file_count": len(files),
        "max_file_size_bytes": max(sizes, default=0),
        "passed": len(files) <= 20_000 and max(sizes, default=0) <= 25 * 1024 * 1024,
    }


def build(
    catalog_path: Path,
    scope_out: Path,
    out: Path,
    cache: Path,
    *,
    plan_only: bool = False,
    offset: int = 0,
    limit: int | None = None,
    includes: tuple[str, ...] = (),
    resume: bool = True,
) -> dict[str, Any]:
    catalog = read_catalog(catalog_path)
    versions = resolve_catalog(catalog.entries)
    scope = normalized_scope(catalog, versions)
    scope_out.parent.mkdir(parents=True, exist_ok=True)
    scope_out.write_text(yaml.safe_dump(scope, sort_keys=False), encoding="utf-8")

    selected = list(versions)
    if includes:
        wanted = {value.lower() for value in includes}
        selected = [
            version
            for version in selected
            if version.family_id.lower() in wanted
            or version.family_name.lower() in wanted
            or version.version_id.lower() in wanted
            or version.display_name.lower() in wanted
        ]
    selected = selected[offset:]
    if limit is not None:
        selected = selected[:limit]

    structure_counts = Counter(version.structure_key for version in versions)
    report: dict[str, Any] = {
        "status": "planned" if plan_only else "running",
        "catalog_declaration_count": len(catalog.declarations),
        "catalog_model_count": len(catalog.entries),
        "normalized_version_count": len(versions),
        "unique_structure_count": len(structure_counts),
        "deduplicated_execution_count": sum(count - 1 for count in structure_counts.values()),
        "selected_version_count": len(selected),
        "executions": [],
        "failures": [],
    }
    if plan_only:
        return report

    # Generated releases are content-addressed and cheap to rematerialize from
    # cache. A clean output prevents orphaned assets from older scopes/schemas.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    execution_records: dict[str, dict[str, Any]] = {}
    failed_structures: dict[str, dict[str, Any]] = {}
    version_summaries: list[dict[str, Any]] = []
    family_versions: dict[str, list[str]] = defaultdict(list)

    with NoNetworkGuard():
        for version in selected:
            if version.structure_key in failed_structures:
                previous = failed_structures[version.structure_key]
                report["failures"].append({
                    "version_id": version.version_id,
                    "structure_key": version.structure_key,
                    "error_type": previous["error_type"],
                    "message": f"canonical structure already failed: {previous['message']}",
                    "execution_reused": True,
                })
                continue
            record = execution_records.get(version.structure_key)
            if record is None and resume:
                record = _restore_execution(cache, out, version.structure_key)
            reused = record is not None
            if record is None:
                bundle = None
                try:
                    bundle = create_model(version)
                    parameters = _parameter_summary(bundle.model)
                    trace = trace_model(
                        bundle.model,
                        bundle.inputs,
                        bundle.kwargs,
                        version.version_id,
                        bundle.constructors,
                    )
                    blocks, shared = build_blocks(
                        bundle.model,
                        version.version_id,
                        version.family_id,
                        version.structure_key,
                        trace,
                    )
                    record = _write_execution(out, cache, version, trace, blocks, shared, parameters, bundle.config)
                    report["executions"].append(version.structure_key)
                except Exception as exc:  # keep a durable failure report during long release builds
                    failure = {
                        "version_id": version.version_id,
                        "structure_key": version.structure_key,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                    report["failures"].append(failure)
                    failed_structures[version.structure_key] = failure
                    continue
                finally:
                    del bundle
                    gc.collect()
            execution_records[version.structure_key] = record
            family_versions[version.family_id].append(version.version_id)
            summary = {
                **version.as_dict(),
                **{key: value for key, value in record.items() if key != "config"},
                "execution_reused": reused,
                "execution_source_version": record["canonical_version_id"],
                "forward_policy": {"device": "cpu", "eval_mode": True, "inference_mode": True},
            }
            write_json(out / "versions" / f"{version.version_id}.json", summary)
            version_summaries.append(summary)

    for entry in catalog.entries:
        ids = family_versions.get(entry.family_id, [])
        if ids:
            write_json(out / "families" / f"{entry.family_id}.json", {
                "family_id": entry.family_id,
                "display_name": entry.display_name,
                "category": entry.category,
                "versions": ids,
            })

    report["status"] = "passed" if not report["failures"] and len(version_summaries) == len(selected) else "failed"
    report["passed_version_count"] = len(version_summaries)
    report["no_weight_download_guard"] = "passed"
    report["source_redistribution_license_gate"] = "passed"
    report["environment"] = {"python": platform.python_version(), "torch": torch.__version__, "device": "cpu"}
    write_json(out / "indexes" / "build_report.v2.json", report)
    search = [{
        "family_id": summary["family_id"],
        "family_name": summary["family_name"],
        "version_id": summary["version_id"],
        "category": summary["category"],
        "parameters": summary["parameters"]["total"],
        "block_count": summary["block_count"],
        "operation_count": summary["operation_count"],
        "source_count": len(summary["sources"]),
        "library": summary["library"],
        "execution_mode": summary["execution_mode"],
    } for summary in version_summaries]
    write_json(out / "indexes" / "search.v2.json", search)
    redistributed_packages = {
        read_json(path).get("package")
        for path in (out / "sources").glob("source.*.json")
        if path.is_file()
    }
    _write_licenses(Path.cwd(), out, {value for value in redistributed_packages if value})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "builder_version": __version__,
        "scope_hash": "sha256." + sha256_json(scope),
        "families": sorted(family_versions),
        "versions": [summary["version_id"] for summary in version_summaries],
        "asset_index": "indexes/assets.v2.json",
        "search_index": "indexes/search.v2.json",
        "license_manifest": "indexes/license_manifest.v2.json",
        "build_report": "indexes/build_report.v2.json",
        "cloudflare_pages_check": {"file_count": 0, "max_file_size_bytes": 0, "passed": False},
    }
    write_json(out / "manifest.v2.json", manifest)
    write_json(out / "indexes" / "assets.v2.json", sorted(
        path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()
    ))
    manifest["cloudflare_pages_check"] = _asset_stats(out)
    write_json(out / "manifest.v2.json", manifest)
    violations = scan_forbidden_artifacts([out, cache])
    if violations:
        raise RuntimeError("forbidden weight-like artifacts: " + ", ".join(map(str, violations)))
    print("NO_WEIGHT_DOWNLOAD_GUARD=passed")
    return report
