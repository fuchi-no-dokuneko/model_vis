from __future__ import annotations

import hashlib
import inspect
from typing import Any

from torch import nn

from .util import sha256_json


def _source_hash(module: nn.Module) -> str:
    try:
        source = inspect.getsource(type(module))
    except (OSError, TypeError):
        source = f"{type(module).__module__}.{type(module).__qualname__}"
    normalized = "\n".join(line.strip() for line in source.splitlines() if line.strip())
    return hashlib.sha256(normalized.encode()).hexdigest()


def _block_type(name: str, module: nn.Module) -> str:
    value = f"{name} {type(module).__name__}".lower()
    for needle, result in (
        ("attention", "attention"), ("mlp", "mlp"), ("embed", "embedding"),
        ("norm", "norm"), ("encoder", "transformer_block"),
        ("decoder", "transformer_block"), ("layer", "transformer_block"),
        ("block", "transformer_block"),
    ):
        if needle in value:
            return result
    return "custom"


def build_blocks(
    model: nn.Module,
    version_id: str,
    family_id: str,
    structure_key: str,
    trace: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    calls_by_module: dict[str, list[dict[str, Any]]] = {}
    for call in trace.get("module_calls", []):
        calls_by_module.setdefault(call["module_id"], []).append(call)
    traced_modules = {item["module_id"]: item for item in trace.get("modules", [])}

    concrete: list[dict[str, Any]] = []
    shared: dict[str, dict[str, Any]] = {}
    for index, (name, module) in enumerate(model.named_modules()):
        if not name or not any(token in name.lower() for token in ("layer", "block", "attention", "mlp", "embed", "norm", "encoder", "decoder")):
            continue
        traced = next((item for item in traced_modules.values() if item["qualified_name"] == name), None)
        if traced is None:
            continue
        parameters = sorted((key, list(value.shape)) for key, value in module.named_parameters(recurse=True))
        buffers = sorted((key, list(value.shape)) for key, value in module.named_buffers(recurse=True))
        child_tree = [(child_name, type(child).__module__, type(child).__qualname__) for child_name, child in module.named_modules()]
        descendant_ids = [
            item["module_id"]
            for item in traced_modules.values()
            if item["qualified_name"] == name or item["qualified_name"].startswith(f"{name}.")
        ]
        calls = [call for module_id in descendant_ids for call in calls_by_module.get(module_id, [])]
        operation_ids = {
            operation_id
            for call in calls
            for operation_id in call.get("operation_ids", [])
        }
        events = [event for event in trace["operations"] if event["op_id"] in operation_ids]
        io_shapes = [
            (
                [item.get("shape") for item in call["input_ports"]],
                [item.get("shape") for item in call["output_ports"]],
            )
            for call in calls
        ]
        topology = [(event["kind"], event["target"]) for event in events]
        signature = {
            "source": _source_hash(module),
            "children": child_tree,
            "topology": topology,
            "parameters": parameters,
            "buffers": buffers,
            "io_shapes": io_shapes,
            "config_branches": [event.get("config_conditions", []) for event in events],
        }
        dedup_uid = "dedup.sha256." + sha256_json(signature)
        block_uid = f"{version_id}.block-{index:05d}"
        shared.setdefault(dedup_uid, {
            "dedup_uid": dedup_uid,
            "signature": signature,
            "operation_ids": sorted(operation_ids),
        })
        concrete.append({
            "block_uid": block_uid,
            "model_version_id": version_id,
            "family_id": family_id,
            "block_type": _block_type(name, module),
            "index": index,
            "module_id": traced["module_id"],
            "parent_module_id": traced["parent_module_id"],
            "layer_group_id": traced["layer_group_id"],
            "qualified_name": name,
            "source_refs": [traced["source_ref"]],
            "input_ports": calls[0]["input_ports"] if calls else [],
            "output_ports": calls[-1]["output_ports"] if calls else [],
            "call_ids": [call["call_id"] for call in calls],
            "operation_ids": sorted(operation_ids),
            "graph_ref": f"graphs/{structure_key}.json",
            "trace_ref": f"traces/{structure_key}.json",
            "dedup_ref": dedup_uid,
            "pointer": {
                "type": "deduplicated_block",
                "target_dedup_uid": dedup_uid,
                "target_asset": f"blocks/shared/{dedup_uid}/block.json",
                "reason": "same_source_tree_graph_shapes_config_signature",
            },
        })
    return concrete, shared
