from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .catalog import read_catalog
from .guard import scan_forbidden_artifacts
from .util import read_json


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _schema_name(relative: Path) -> str | None:
    value = relative.as_posix()
    if value in {"manifest.v1.json", "manifest.v2.json"}:
        return "manifest.v1.schema.json"
    if value.startswith("families/"):
        return "family.v1.schema.json"
    if value.startswith("versions/"):
        return "version.v1.schema.json"
    if value.startswith("traces/"):
        return "trace.v1.schema.json"
    if value.startswith("graphs/"):
        return "graph.v1.schema.json"
    if value.startswith("blocks/"):
        return "blocks.v1.schema.json"
    if value.startswith("configs/"):
        return "config.v1.schema.json"
    if value.startswith("sources/"):
        return "source.v1.schema.json"
    return {
        "indexes/search.v1.json": "search-index.v1.schema.json",
        "indexes/search.v2.json": "search-index.v1.schema.json",
        "indexes/assets.v1.json": "asset-index.v1.schema.json",
        "indexes/assets.v2.json": "asset-index.v1.schema.json",
        "indexes/license_manifest.v1.json": "license-index.v1.schema.json",
        "indexes/license_manifest.v2.json": "license-index.v1.schema.json",
        "indexes/build_report.v1.json": "build-report.v1.schema.json",
        "indexes/build_report.v2.json": "build-report.v1.schema.json",
    }.get(value)


def validate(
    model_code: Path,
    catalog_path: Path,
    cloudflare_target: str = "free",
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = model_code / "manifest.v2.json"
    if not manifest_path.is_file():
        return {"passed": False, "errors": [f"missing {manifest_path}"]}
    manifest = read_json(manifest_path)
    catalog = read_catalog(catalog_path)
    report = read_json(model_code / manifest["build_report"])
    for path in model_code.rglob("*.json"):
        relative = path.relative_to(model_code)
        schema_name = _schema_name(relative)
        if schema_name is None:
            errors.append(f"no schema is assigned to {relative}")
            continue
        try:
            instance = read_json(path)
            schema = read_json(SCHEMA_ROOT / schema_name)
            validation_errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda item: list(item.path))
            errors.extend(f"{relative}: {item.message}" for item in validation_errors)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: {exc}")
    expected = {entry.family_id for entry in catalog.entries}
    actual = set(manifest["families"])
    if allow_partial and not actual:
        errors.append("partial build contains no families")
    elif allow_partial and not actual <= expected:
        errors.append(f"partial build has unknown families: {sorted(actual - expected)}")
    elif not allow_partial and expected != actual:
        errors.append(f"family coverage mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    if report["status"] != "passed":
        errors.append(f"build report status is {report['status']!r}")
    for version_id in manifest["versions"]:
        path = model_code / "versions" / f"{version_id}.json"
        if not path.is_file():
            errors.append(f"missing version asset {path}")
            continue
        version = read_json(path)
        if version.get("status") != "passed" or version.get("trace_event_count", 0) <= 0:
            errors.append(f"version did not pass a real trace: {version_id}")
        if not version.get("top_level_outputs"):
            errors.append(f"version has no top-level output summary: {version_id}")
        graph_path = model_code / version.get("graph_ref", "")
        if graph_path.is_file():
            graph = read_json(graph_path)
            node_ids = {node["id"] for node in graph.get("nodes", [])}
            tensor_ids = {tensor["tensor_id"] for tensor in graph.get("tensors", [])}
            tensors = {tensor["tensor_id"]: tensor for tensor in graph.get("tensors", [])}
            modules = {module["module_id"]: module for module in graph.get("modules", [])}
            calls = {call["call_id"]: call for call in graph.get("module_calls", [])}
            input_ports: dict[str, tuple[str, dict[str, Any]]] = {}
            output_ports: dict[str, tuple[str, dict[str, Any]]] = {}
            for node in graph.get("nodes", []):
                for port in node.get("input_ports", []):
                    input_ports[port["port_id"]] = (node["id"], port)
                for port in node.get("output_ports", []):
                    output_ports[port["port_id"]] = (node["id"], port)
            port_ids = set(input_ports) | set(output_ports)
            if graph.get("node_count") != len(node_ids) or graph.get("edge_count") != len(graph.get("edges", [])):
                errors.append(f"graph count mismatch: {version_id}")
            if len(port_ids) != sum(
                len(node.get("input_ports", [])) + len(node.get("output_ports", []))
                for node in graph.get("nodes", [])
            ):
                errors.append(f"graph has duplicate port IDs: {version_id}")
            consumed_ports: set[str] = set()
            for edge in graph.get("edges", []):
                if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
                    errors.append(f"graph edge references unknown node: {version_id}:{edge.get('edge_id')}")
                if edge.get("source_port") not in port_ids or edge.get("target_port") not in port_ids:
                    errors.append(f"graph edge references unknown port: {version_id}:{edge.get('edge_id')}")
                if edge.get("tensor_id") not in tensor_ids:
                    errors.append(f"graph edge references unknown tensor: {version_id}:{edge.get('edge_id')}")
                source = output_ports.get(edge.get("source_port"))
                target = input_ports.get(edge.get("target_port"))
                if source and source[0] != edge.get("source"):
                    errors.append(f"graph edge source port owner mismatch: {version_id}:{edge.get('edge_id')}")
                if target and target[0] != edge.get("target"):
                    errors.append(f"graph edge target port owner mismatch: {version_id}:{edge.get('edge_id')}")
                if target and target[1].get("tensor_id") != edge.get("tensor_id"):
                    errors.append(f"graph edge target tensor mismatch: {version_id}:{edge.get('edge_id')}")
                if source and edge.get("confidence") != "lineage" and source[1].get("tensor_id") != edge.get("tensor_id"):
                    errors.append(f"graph edge source tensor mismatch: {version_id}:{edge.get('edge_id')}")
                if edge.get("target_port") in consumed_ports:
                    errors.append(f"graph input port has multiple producers: {version_id}:{edge.get('target_port')}")
                consumed_ports.add(edge.get("target_port"))
            missing_routes = sorted(set(input_ports) - consumed_ports)
            if missing_routes:
                errors.append(f"graph input ports have no producer routes: {version_id}:{missing_routes[:5]}")
            for node in graph.get("nodes", []):
                for port in [*node.get("input_ports", []), *node.get("output_ports", [])]:
                    tensor = tensors.get(port.get("tensor_id"))
                    if tensor is None:
                        errors.append(f"graph port references unknown tensor: {version_id}:{port.get('port_id')}")
                        continue
                    for key in ("shape", "dtype", "device"):
                        if port.get(key) != tensor.get(key):
                            errors.append(f"graph port {key} differs from tensor: {version_id}:{port.get('port_id')}")
                    if port.get("required") == port.get("optional"):
                        errors.append(f"graph port required/optional flags are invalid: {version_id}:{port.get('port_id')}")
            if not modules:
                errors.append(f"graph has no module hierarchy: {version_id}")
            for module_id, module in modules.items():
                parent_id = module.get("parent_module_id")
                if parent_id and parent_id not in modules:
                    errors.append(f"module has unknown parent: {version_id}:{module_id}")
                for child_id in module.get("child_module_ids", []):
                    if child_id not in modules or modules[child_id].get("parent_module_id") != module_id:
                        errors.append(f"module child relationship is inconsistent: {version_id}:{module_id}:{child_id}")
                constructor = module.get("constructor", {})
                if constructor.get("capture_confidence") != "actual_call":
                    errors.append(f"module constructor call form was not captured: {version_id}:{module_id}")
                for argument in constructor.get("effective_arguments", []):
                    if argument.get("origin") == "config" and not argument.get("config_path"):
                        errors.append(f"constructor config origin has no path: {version_id}:{module_id}:{argument.get('name')}")
                for call_id in module.get("call_ids", []):
                    if call_id not in calls or calls[call_id].get("module_id") != module_id:
                        errors.append(f"module call relationship is inconsistent: {version_id}:{module_id}:{call_id}")
            for call_id, call in calls.items():
                if call.get("module_id") not in modules:
                    errors.append(f"call references unknown module: {version_id}:{call_id}")
                parent_call = call.get("parent_call_id")
                if parent_call and parent_call not in calls:
                    errors.append(f"call references unknown parent call: {version_id}:{call_id}")
                for port in [*call.get("input_ports", []), *call.get("output_ports", [])]:
                    if port.get("tensor_id") not in tensor_ids:
                        errors.append(f"call port references unknown tensor: {version_id}:{call_id}:{port.get('port_id')}")
            layer_ids = set()
            for group in graph.get("layer_groups", []):
                layer_id = group.get("layer_group_id")
                if layer_id in layer_ids or group.get("module_id") not in modules:
                    errors.append(f"layer group identity is invalid: {version_id}:{layer_id}")
                layer_ids.add(layer_id)
                if not str(group.get("structural_signature", "")).startswith("structure.sha256."):
                    errors.append(f"layer structural signature is missing: {version_id}:{layer_id}")
                if not str(group.get("runtime_signature", "")).startswith("layer.sha256."):
                    errors.append(f"layer runtime signature is missing: {version_id}:{layer_id}")
            if graph.get("trace_modes", {}).get("exact_lineage") != "completed":
                errors.append(f"exact lineage trace did not complete: {version_id}")
            confidence_counts = graph.get("trace_modes", {}).get("confidence_counts", {})
            if sum(confidence_counts.values()) != len(graph.get("edges", [])):
                errors.append(f"trace confidence counts do not match edges: {version_id}")
    for source_path in (model_code / "sources").glob("source.*.json"):
        source = read_json(source_path)
        asset_path = model_code / source.get("asset_path", "")
        if not asset_path.is_file():
            errors.append(f"missing redistributed source body: {source_path.name}")
            continue
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if source.get("content_hash") != f"sha256.{digest}":
            errors.append(f"source content hash mismatch: {source_path.name}")
        if source.get("package") in {"torch", "transformers", "diffusers"} and not source.get("repository_file_url"):
            errors.append(f"source official repository URL missing: {source_path.name}")
    if report.get("passed_version_count") != len(manifest["versions"]):
        errors.append("manifest version count does not match passed build-report count")
    if report.get("source_redistribution_license_gate") != "passed":
        errors.append("source redistribution license gate did not pass")
    license_manifest = read_json(model_code / manifest["license_manifest"])
    for item in license_manifest:
        if not item.get("source_redistributed"):
            continue
        if not item.get("license_assets"):
            errors.append(f"redistributed package has no packaged license text: {item.get('package')}")
        for relative in item.get("license_assets", []):
            if not (model_code / relative).is_file():
                errors.append(f"missing packaged license text: {relative}")
    limits = manifest["cloudflare_pages_check"]
    file_limit = 20_000 if cloudflare_target == "free" else 100_000
    if limits["file_count"] > file_limit or limits["max_file_size_bytes"] > 25 * 1024 * 1024:
        errors.append("Cloudflare Pages asset limits exceeded")
    forbidden = scan_forbidden_artifacts([model_code])
    if forbidden:
        errors.append("forbidden artifacts: " + ", ".join(map(str, forbidden)))
    return {"passed": not errors, "errors": errors, "version_count": len(manifest["versions"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated model assets")
    parser.add_argument("--model-code", type=Path, default=Path("model_code"))
    parser.add_argument("--catalog", type=Path, default=Path("model.txt"))
    parser.add_argument("--scope", type=Path, default=Path("model_scope.generated.yaml"))
    parser.add_argument("--cloudflare-target", choices=("free", "paid"), default="free")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Validate a development subset while retaining strict full-catalog validation by default",
    )
    args = parser.parse_args()
    result = validate(
        args.model_code,
        args.catalog,
        args.cloudflare_target,
        allow_partial=args.allow_partial,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
