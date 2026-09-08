from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .catalog import read_catalog
from .guard import scan_forbidden_artifacts
from .semantics import (
    INTERFACE_TAGS_REF,
    SEMANTIC_GENERATOR_VERSION,
    SEMANTIC_REPORT_REF,
    SEMANTIC_SCHEMA_REF,
    load_registry,
)
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
    if value.startswith("semantics/"):
        return "semantic-model.v1.schema.json"
    return {
        "indexes/search.v1.json": "search-index.v1.schema.json",
        "indexes/search.v2.json": "search-index.v1.schema.json",
        "indexes/assets.v1.json": "asset-index.v1.schema.json",
        "indexes/assets.v2.json": "asset-index.v1.schema.json",
        "indexes/license_manifest.v1.json": "license-index.v1.schema.json",
        "indexes/license_manifest.v2.json": "license-index.v1.schema.json",
        "indexes/build_report.v1.json": "build-report.v1.schema.json",
        "indexes/build_report.v2.json": "build-report.v1.schema.json",
        "indexes/semantic.v1.json": "semantic-index.v1.schema.json",
        "indexes/semantic-report.v1.json": "semantic-report.v1.schema.json",
        "contracts/interface-tags.v1.json": "interface-tags.v1.schema.json",
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
    semantic_index_ref = manifest.get("semantic_index")
    if not semantic_index_ref or not (model_code / semantic_index_ref).is_file():
        errors.append("manifest semantic index is missing")
        semantic_index = {"versions": []}
    else:
        semantic_index = read_json(model_code / semantic_index_ref)
    semantic_report_ref = manifest.get("semantic_report")
    if not semantic_report_ref or not (model_code / semantic_report_ref).is_file():
        errors.append("manifest semantic report is missing")
        semantic_report = {"catalog": {}, "counts": {}, "models": [], "failures": []}
    else:
        semantic_report = read_json(model_code / semantic_report_ref)
    catalog = read_catalog(catalog_path)
    report = read_json(model_code / manifest["build_report"])
    for path in model_code.rglob("*.json"):
        relative = path.relative_to(model_code)
        if relative.as_posix() == SEMANTIC_SCHEMA_REF:
            try:
                published_schema = read_json(path)
                canonical_schema = read_json(SCHEMA_ROOT / "semantic-model.v1.schema.json")
                if published_schema != canonical_schema:
                    errors.append(f"{relative}: published semantic schema differs from the canonical schema")
                Draft202012Validator.check_schema(published_schema)
            except (OSError, ValueError, json.JSONDecodeError, SchemaError) as exc:
                errors.append(f"{relative}: {exc}")
            continue
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
    contracts = manifest.get("semantic_contracts") or {}
    expected_contracts = {
        "schema_ref": SEMANTIC_SCHEMA_REF,
        "interface_tags_ref": INTERFACE_TAGS_REF,
    }
    if contracts != expected_contracts:
        errors.append("manifest semantic contract references are invalid")
    for relative in expected_contracts.values():
        if not (model_code / relative).is_file():
            errors.append(f"missing published semantic contract: {relative}")
    interface_tags_path = model_code / INTERFACE_TAGS_REF
    if interface_tags_path.is_file() and read_json(interface_tags_path) != load_registry():
        errors.append("published interface-tag registry differs from the canonical registry")
    expected = {entry.family_id for entry in catalog.entries}
    actual = set(manifest["families"])
    if allow_partial and not actual:
        errors.append("partial build contains no families")
    elif allow_partial and not actual <= expected:
        errors.append(f"partial build has unknown families: {sorted(actual - expected)}")
    elif not allow_partial and expected != actual:
        errors.append(f"family coverage mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    if report["status"] not in {"passed", "passed_with_warnings"}:
        errors.append(f"build report status is {report['status']!r}")
    semantic_assets: dict[str, dict[str, Any]] = {}
    for version_id in manifest["versions"]:
        path = model_code / "versions" / f"{version_id}.json"
        if not path.is_file():
            errors.append(f"missing version asset {path}")
            continue
        version = read_json(path)
        if version.get("status") not in {"passed", "partial"} or version.get("trace_event_count", 0) <= 0:
            errors.append(f"version did not pass a real trace: {version_id}")
        if version.get("status") == "partial" and not version.get("warnings"):
            errors.append(f"partial version has no model-specific warning: {version_id}")
        security = version.get("security_policy", {})
        if any((
            security.get("weights_downloaded") is not False,
            security.get("remote_code_executed") is not False,
            security.get("trust_remote_code") is not False,
            security.get("network_during_trace") is not False,
        )):
            errors.append(f"version security policy is missing or unsafe: {version_id}")
        trace_config_path = model_code / version.get("trace_config_ref", "")
        if version.get("trace_config_ref") and not trace_config_path.is_file():
            errors.append(f"missing trace config record: {version_id}")
        source = version.get("official_config_source")
        if source:
            official_path = model_code / version.get("official_config_ref", "")
            diff_path = model_code / version.get("config_diff_ref", "")
            if not official_path.is_file():
                errors.append(f"missing raw official config: {version_id}")
            else:
                digest = hashlib.sha256(official_path.read_bytes()).hexdigest()
                if source.get("sha256") != digest:
                    errors.append(f"official config hash mismatch: {version_id}")
            revision = source.get("revision", "")
            if len(revision) != 40 or any(value not in "0123456789abcdef" for value in revision):
                errors.append(f"official config revision is not a full SHA: {version_id}")
            if revision not in source.get("pinned_url", ""):
                errors.append(f"official config URL is not pinned to its revision: {version_id}")
            if not diff_path.is_file():
                errors.append(f"missing official/trace config diff: {version_id}")
        if not version.get("top_level_outputs"):
            errors.append(f"version has no top-level output summary: {version_id}")
        graph_path = model_code / version.get("graph_ref", "")
        if graph_path.is_file():
            graph = read_json(graph_path)
            node_ids = {node["id"] for node in graph.get("nodes", [])}
            nodes_by_id = {node["id"]: node for node in graph.get("nodes", [])}
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
            semantic_path = model_code / version.get("semantic_ref", "")
            if not version.get("semantic_ref") or not semantic_path.is_file():
                errors.append(f"missing semantic asset: {version_id}")
            else:
                semantic = read_json(semantic_path)
                semantic_assets[version_id] = semantic
                if semantic.get("generated_at") != manifest.get("semantic_generated_at"):
                    errors.append(f"semantic generated timestamp differs from manifest: {version_id}")
                if semantic.get("generator_version") != manifest.get("semantic_generator_version"):
                    errors.append(f"semantic generator version differs from manifest: {version_id}")
                semantic_stages = {stage["stage_id"]: stage for stage in semantic.get("stages", [])}
                semantic_entities = semantic.get("entities", {})
                graph_entity_ids = node_ids | set(modules)
                operation_ids = {node["id"] for node in graph.get("nodes", []) if node.get("kind") == "aten_op"}
                known_tags = {
                    "input", "embedding_or_projection", "position_or_context", "attention_or_mixer",
                    "feed_forward", "normalization_or_residual", "aggregation_or_decoder",
                    "output_or_head", "other",
                }
                if set(semantic_entities) != graph_entity_ids:
                    errors.append(f"semantic entity coverage mismatch: {version_id}")
                for entity_id, entity in semantic_entities.items():
                    if entity.get("entity_id") != entity_id:
                        errors.append(f"semantic entity identity mismatch: {version_id}:{entity_id}")
                    if entity.get("stage_id") not in semantic_stages:
                        errors.append(f"semantic entity references unknown stage: {version_id}:{entity_id}")
                    if not set(entity.get("tags", [])) <= known_tags:
                        errors.append(f"semantic entity has unknown tag: {version_id}:{entity_id}")
                    if not (set(entity.get("input_tensor_ids", [])) | set(entity.get("output_tensor_ids", []))) <= tensor_ids:
                        errors.append(f"semantic entity references unknown tensor: {version_id}:{entity_id}")
                stage_orders = {stage_id: stage.get("order", -1) for stage_id, stage in semantic_stages.items()}
                if sorted(stage_orders.values()) != list(range(len(stage_orders))):
                    errors.append(f"semantic stage order is not contiguous: {version_id}")
                for stage_id, stage in semantic_stages.items():
                    if not stage.get("entity_ids"):
                        errors.append(f"semantic stage has no entities: {version_id}:{stage_id}")
                    if not set(stage.get("entity_ids", [])) <= set(semantic_entities):
                        errors.append(f"semantic stage references unknown entity: {version_id}:{stage_id}")
                    if not set(stage.get("module_ids", [])) <= set(modules):
                        errors.append(f"semantic stage references unknown module: {version_id}:{stage_id}")
                    if not set(stage.get("operation_ids", [])) <= operation_ids:
                        errors.append(f"semantic stage references unknown operation: {version_id}:{stage_id}")
                    if not (set(stage.get("input_tensor_ids", [])) | set(stage.get("output_tensor_ids", []))) <= tensor_ids:
                        errors.append(f"semantic stage references unknown tensor: {version_id}:{stage_id}")
                for edge in semantic.get("stage_edges", []):
                    source_order = stage_orders.get(edge.get("source_stage_id"), -1)
                    target_order = stage_orders.get(edge.get("target_stage_id"), -1)
                    if source_order < 0 or target_order < 0 or source_order >= target_order:
                        errors.append(f"semantic stage edge violates topological order: {version_id}")
                metrics = semantic.get("metrics", {})
                evidence = version.get("parameter_evidence", {})
                if metrics.get("official_parameter_estimate") != evidence.get("parameter_count"):
                    errors.append(f"semantic parameter evidence mismatch: {version_id}")
                if evidence.get("parameter_count") is not None and not version.get("official_config_source"):
                    errors.append(f"parameter count lacks selected model provenance: {version_id}")
                parameter_values = metrics.get("parameter_distribution", [])
                operation_values = metrics.get("operation_distribution", [])
                if sum(item.get("value", 0) for item in parameter_values) != version.get("parameters", {}).get("total"):
                    errors.append(f"semantic parameter distribution total mismatch: {version_id}")
                if sum(item.get("value", 0) for item in operation_values) != len(operation_ids):
                    errors.append(f"semantic operation distribution total mismatch: {version_id}")
                allowed_distribution_stages = set(semantic_stages) | {"unclassified"}
                if any(item.get("stage_id") not in allowed_distribution_stages for item in [*parameter_values, *operation_values]):
                    errors.append(f"semantic distribution references unknown stage: {version_id}")
                for journey in semantic.get("journeys", []):
                    for step in journey.get("steps", []):
                        tensor = tensors.get(step.get("tensor_id"))
                        if tensor is None or tensor.get("shape") != step.get("shape"):
                            errors.append(f"semantic journey tensor shape mismatch: {version_id}:{step.get('step_id')}")
                        node = nodes_by_id.get(step.get("node_id"), {})
                        for direction in ("input_ports", "output_ports"):
                            actual = step.get(direction, [])
                            expected = node.get(direction, [])
                            keys = ("port_id", "tensor_id", "name", "shape", "dtype")
                            if actual != [{key: port[key] for key in keys if key in port} for port in expected]:
                                errors.append(f"semantic journey operation ports mismatch: {version_id}:{step.get('step_id')}:{direction}")
    semantic_index_versions = {item.get("version_id"): item for item in semantic_index.get("versions", [])}
    if semantic_index.get("generated_at") != manifest.get("semantic_generated_at"):
        errors.append("semantic index timestamp differs from manifest")
    if semantic_index.get("generator_version") != SEMANTIC_GENERATOR_VERSION:
        errors.append("semantic index generator version is invalid")
    if semantic_index.get("semantic_schema_ref") != SEMANTIC_SCHEMA_REF:
        errors.append("semantic index schema contract reference is invalid")
    if semantic_index.get("interface_tags_ref") != INTERFACE_TAGS_REF:
        errors.append("semantic index tag-registry reference is invalid")
    if semantic_index.get("report_ref") != SEMANTIC_REPORT_REF:
        errors.append("semantic index report reference is invalid")
    if set(semantic_index_versions) != set(manifest["versions"]):
        errors.append("semantic index version coverage mismatch")
    for version_id, item in semantic_index_versions.items():
        expected_ref = f"semantics/{version_id}.json"
        if item.get("semantic_ref") != expected_ref or not (model_code / expected_ref).is_file():
            errors.append(f"semantic index target is invalid: {version_id}")
            continue
        semantic = semantic_assets.get(version_id, {})
        version = read_json(model_code / "versions" / f"{version_id}.json")
        has_fallback = any(
            entity.get("confidence") == "technical_fallback" or entity.get("primary_tag") == "other"
            for entity in semantic.get("entities", {}).values()
        )
        expected_status = (
            "partial" if version.get("status") == "partial"
            else "fallback" if has_fallback
            else "passed"
        )
        if item.get("generation_status") != expected_status:
            errors.append(f"semantic index generation status is invalid: {version_id}")
        if item.get("stage_count") != len(semantic.get("stages", [])):
            errors.append(f"semantic index stage count is invalid: {version_id}")
        if item.get("coverage") != semantic.get("coverage"):
            errors.append(f"semantic index coverage differs from semantic asset: {version_id}")

    if semantic_report.get("generated_at") != manifest.get("semantic_generated_at"):
        errors.append("semantic report timestamp differs from manifest")
    if semantic_report.get("generator_version") != SEMANTIC_GENERATOR_VERSION:
        errors.append("semantic report generator version is invalid")
    catalog_summary = semantic_report.get("catalog", {})
    expected_catalog_summary = {
        "family_count": len(catalog.entries),
        "normalized_version_count": int(report.get("normalized_version_count") or 0),
        "selected_family_count": len(manifest["families"]),
        "selected_version_count": int(report.get("selected_version_count") or 0),
        "generated_family_count": len(manifest["families"]),
        "generated_version_count": len(manifest["versions"]),
    }
    for name, value in expected_catalog_summary.items():
        if catalog_summary.get(name) != value:
            errors.append(f"semantic report catalog count is invalid: {name}")
    family_count = expected_catalog_summary["family_count"]
    version_count = expected_catalog_summary["normalized_version_count"]
    expected_family_fraction = round(expected_catalog_summary["generated_family_count"] / family_count, 6) if family_count else 1.0
    expected_version_fraction = round(expected_catalog_summary["generated_version_count"] / version_count, 6) if version_count else 1.0
    if catalog_summary.get("generated_family_fraction") != expected_family_fraction:
        errors.append("semantic report generated-family fraction is invalid")
    if catalog_summary.get("generated_version_fraction") != expected_version_fraction:
        errors.append("semantic report generated-version fraction is invalid")
    expected_status_counts = {
        name: sum(item.get("generation_status") == name for item in semantic_index_versions.values())
        for name in ("passed", "fallback", "partial")
    }
    expected_status_counts["failed"] = len(report.get("failures", []))
    if semantic_report.get("counts") != expected_status_counts:
        errors.append("semantic report status counts differ from the semantic index/build report")
    report_models = {item.get("version_id"): item for item in semantic_report.get("models", [])}
    expected_report_model_ids = set(manifest["versions"]) | {
        str(item.get("version_id") or "unknown") for item in report.get("failures", [])
    }
    if set(report_models) != expected_report_model_ids:
        errors.append("semantic report model coverage mismatch")
    for version_id, item in semantic_index_versions.items():
        report_model = report_models.get(version_id, {})
        if (
            report_model.get("status") != item.get("generation_status")
            or report_model.get("semantic_ref") != item.get("semantic_ref")
            or report_model.get("coverage") != item.get("coverage")
        ):
            errors.append(f"semantic report model record differs from index: {version_id}")
    expected_failures = [{
        "version_id": str(item.get("version_id") or "unknown"),
        "error_type": str(item.get("error_type") or "unknown"),
        "message": str(item.get("message") or ""),
    } for item in report.get("failures", [])]
    if semantic_report.get("failures") != expected_failures:
        errors.append("semantic report failure details differ from build report")
    expected_remaining = []
    unselected_family_count = max(0, expected_catalog_summary["family_count"] - expected_catalog_summary["selected_family_count"])
    unselected_count = max(0, expected_catalog_summary["normalized_version_count"] - expected_catalog_summary["selected_version_count"])
    failed_selected_family_count = max(0, expected_catalog_summary["selected_family_count"] - expected_catalog_summary["generated_family_count"])
    failed_selected_count = max(0, expected_catalog_summary["selected_version_count"] - expected_catalog_summary["generated_version_count"])
    if unselected_family_count or unselected_count:
        expected_remaining.append({
            "reason": "outside_selected_build_scope",
            "family_count": unselected_family_count,
            "version_count": unselected_count,
        })
    if failed_selected_family_count or failed_selected_count:
        expected_remaining.append({
            "reason": "build_failed",
            "family_count": failed_selected_family_count,
            "version_count": failed_selected_count,
        })
    if semantic_report.get("remaining_reasons") != expected_remaining:
        errors.append("semantic report remaining-model reasons are invalid")
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
