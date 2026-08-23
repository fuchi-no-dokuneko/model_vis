from __future__ import annotations

import argparse
import datetime as dt
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .util import read_json, slug, write_json


SEMANTIC_SCHEMA_VERSION = "1.0.0"
TAG_VOCAB_VERSION = "1.0.0"
SEMANTIC_GENERATOR_VERSION = "1.0.0"
SEMANTIC_SCHEMA_REF = "contracts/semantic-model.schema.json"
INTERFACE_TAGS_REF = "contracts/interface-tags.v1.json"
SEMANTIC_REPORT_REF = "indexes/semantic-report.v1.json"
PROFILE_ROOT = Path(__file__).parents[2] / "profiles"
SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"
STAGE_NAMES = {
    "input_adapter": "Model input",
    "preprocessing": "Preprocessing",
    "tokenization": "Tokenization",
    "input_embedding": "Input projection",
    "position_encoding": "Position and context",
    "backbone": "Backbone processing",
    "attention": "Attention and mixing",
    "state_space_or_recurrence": "State-space or recurrent mixing",
    "feed_forward": "Feed-forward transformation",
    "normalization": "Normalization",
    "residual_and_scaling": "Residual and scaling",
    "cross_modal_fusion": "Cross-modal fusion",
    "aggregation": "Aggregation",
    "task_head": "Task head",
    "output_adapter": "Model output",
    "loss_or_training_only": "Training-only computation",
    "other": "Unclassified",
}
TAG_NAMES = {
    "input": "Model input",
    "embedding_or_projection": "Embedding or projection",
    "position_or_context": "Position or context",
    "attention_or_mixer": "Attention or mixer",
    "feed_forward": "Feed-forward transform",
    "normalization_or_residual": "Normalization or residual",
    "aggregation_or_decoder": "Aggregation or decoder",
    "output_or_head": "Model output or head",
    "other": "Unclassified component",
}
TAG_TO_STAGE = {
    "input": "input_adapter",
    "embedding_or_projection": "input_embedding",
    "position_or_context": "position_encoding",
    "attention_or_mixer": "attention",
    "feed_forward": "feed_forward",
    "normalization_or_residual": "normalization",
    "aggregation_or_decoder": "aggregation",
    "output_or_head": "task_head",
    "other": "backbone",
}
STAGE_PRIORITY = {
    "attention": 0,
    "state_space_or_recurrence": 0,
    "feed_forward": 1,
    "position_encoding": 2,
    "normalization": 2,
    "residual_and_scaling": 2,
    "tokenization": 3,
    "input_embedding": 3,
    "aggregation": 3,
    "task_head": 3,
    "backbone": 8,
    "other": 9,
}
ROUTE_CONFIDENCE = {"unresolved": 0, "ambiguous": 1, "inferred": 2, "lineage": 3, "exact": 4}


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry = read_json(path or PROFILE_ROOT / "interface-tags.v1.json")
    expected = set(TAG_TO_STAGE)
    actual = {item.get("id") for item in registry.get("tags", [])}
    if registry.get("schema_version") != TAG_VOCAB_VERSION or actual != expected:
        raise ValueError(f"invalid class/interface tag registry: expected {sorted(expected)}, got {sorted(actual)}")
    return registry


def load_stage_rules(path: Path | None = None) -> dict[str, Any]:
    rules = read_json(path or PROFILE_ROOT / "semantic-stage-rules.v1.json")
    if rules.get("schema_version") != SEMANTIC_SCHEMA_VERSION:
        raise ValueError("invalid semantic stage rule revision")
    return rules


def _interface_text(module: dict[str, Any]) -> str:
    interface = module.get("forward_interface") or {}
    if interface.get("text"):
        return str(interface["text"])
    parameters: list[str] = []
    for call in module.get("call_ids", []):
        if call:
            break
    symbol = (module.get("source_ref") or {}).get("symbol") or "forward"
    return f"{str(symbol).rsplit('.', 1)[-1]}({', '.join(parameters)})"


def assign_class_tags(module: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    """Apply exact class, base-class, then verified-interface rules in that order."""
    class_name = module.get("class_name")
    base_classes = set(module.get("base_classes") or [])
    interface = _interface_text(module)
    for rule_kind, predicate in (
        ("exact_class_rule", lambda tag: class_name in set(tag.get("exact_classes") or [])),
        ("exact_base_class_rule", lambda tag: bool(base_classes & set(tag.get("base_classes") or []))),
        ("verified_signature_rule", lambda tag: interface in set(tag.get("verified_signatures") or [])),
    ):
        matches = [tag["id"] for tag in registry["tags"] if tag["id"] != "other" and predicate(tag)]
        if matches:
            return {"tags": matches, "primary_tag": matches[0], "confidence": "verified_rule", "provenance": [rule_kind, "trace"]}
    return {"tags": ["other"], "primary_tag": "other", "confidence": "technical_fallback", "provenance": ["no_exact_interface_rule", "trace"]}


def _domain(version: dict[str, Any]) -> str:
    value = str(version.get("task_type") or version.get("category") or "").lower()
    for domain in ("audio", "vision", "text", "multimodal"):
        if domain in value:
            return domain
    return "other"


def _matching_rule_packs(domain: str, config: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    result = []
    for pack in rules.get("rule_packs", []):
        predicates = pack.get("when", {})
        if predicates.get("domain") not in {None, domain}:
            continue
        if predicates.get("model_types") and config.get("model_type") not in predicates["model_types"]:
            continue
        if "is_encoder_decoder" in predicates and config.get("is_encoder_decoder") != predicates["is_encoder_decoder"]:
            continue
        result.append(pack["id"])
    return result


def topological_node_ids(graph: dict[str, Any]) -> list[str]:
    nodes = [node["id"] for node in graph.get("nodes", [])]
    original = {node_id: index for index, node_id in enumerate(nodes)}
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {node_id: 0 for node_id in nodes}
    for edge in graph.get("edges", []):
        source, target = edge.get("source"), edge.get("target")
        if source not in indegree or target not in indegree or source == target or target in outgoing[source]:
            continue
        outgoing[source].add(target)
        indegree[target] += 1
    ready = sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=original.get)
    result = []
    while ready:
        node_id = ready.pop(0)
        result.append(node_id)
        for target in sorted(outgoing[node_id], key=original.get):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=original.get)
    result.extend(node_id for node_id in nodes if node_id not in set(result))
    return result


def _module_stage_hints(
    modules: list[dict[str, Any]],
    tag_records: dict[str, dict[str, Any]],
    stage_rules: dict[str, Any],
    active_rule_pack_ids: list[str],
) -> dict[str, tuple[str, int, str]]:
    exact = stage_rules.get("exact_class_stages", {})
    active_packs = [
        pack for pack in stage_rules.get("rule_packs", [])
        if pack.get("id") in active_rule_pack_ids
    ]
    result = {}
    for module in modules:
        module_id = module["module_id"]
        if module.get("class_name") in exact:
            result[module_id] = (exact[module["class_name"]], 0, "exact_class_stage_rule")
        else:
            tag = tag_records[module_id]["primary_tag"]
            pack_match = next(
                (
                    (pack["tag_stages"][tag], pack["id"])
                    for pack in active_packs
                    if tag in pack.get("tag_stages", {})
                ),
                None,
            )
            stage_type = pack_match[0] if pack_match else TAG_TO_STAGE[tag]
            provenance = (
                f"architecture_family_rule:{pack_match[1]}"
                if pack_match else ("class_tag_stage_rule" if tag != "other" else "topology_stage_inference")
            )
            result[module_id] = (stage_type, 1 if tag != "other" else 2, provenance)
    return result


def _repeated_anchor(
    module_id: str | None,
    modules_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the outer traced repeated block, not nested repeated implementation leaves."""
    candidates = []
    current = modules_by_id.get(module_id or "")
    while current:
        display = str(current.get("display_name") or "").lower()
        parent = modules_by_id.get(current.get("parent_module_id") or "")
        parent_is_sequence = (parent or {}).get("class_name") in {
            "torch.nn.modules.container.ModuleList",
            "torch.nn.modules.container.Sequential",
        }
        if current.get("layer_group_id") and (
            parent_is_sequence or any(token in display for token in ("layer", "block", "stage", "expert"))
        ):
            candidates.append(current)
        current = modules_by_id.get(current.get("parent_module_id") or "")
    return candidates[-1] if candidates else None


def _effective_stage_hint(
    module_id: str | None,
    modules_by_id: dict[str, dict[str, Any]],
    hints: dict[str, tuple[str, int, str]],
) -> tuple[str, int, str]:
    candidates = []
    current = modules_by_id.get(module_id or "")
    distance = 0
    while current:
        stage_type, strength, provenance = hints[current["module_id"]]
        candidates.append((strength, STAGE_PRIORITY.get(stage_type, 9), distance, stage_type, provenance))
        current = modules_by_id.get(current.get("parent_module_id") or "")
        distance += 1
    if not candidates:
        return "other", 2, "topology_stage_inference"
    strength, _, _, stage_type, provenance = min(candidates)
    return stage_type, strength, provenance


def _shape_product(shape: Iterable[int]) -> int:
    return math.prod(int(value) for value in shape)


def _unique_ports(items: Iterable[dict[str, Any]]) -> tuple[list[str], list[list[int]]]:
    ids, shapes, seen = [], [], set()
    for port in items:
        tensor_id = port.get("tensor_id")
        if not tensor_id or tensor_id in seen:
            continue
        seen.add(tensor_id)
        ids.append(tensor_id)
        shapes.append(list(port.get("shape") or []))
    return ids, shapes


def _technical_explanation(source_name: str, inputs: list[list[int]], outputs: list[list[int]]) -> str:
    if inputs and outputs:
        return f"Technical fallback: {source_name} transforms {inputs[0]} into {outputs[0]} in the observed trace."
    if outputs:
        return f"Technical fallback: {source_name} produces {outputs[0]} in the observed trace."
    if inputs:
        return f"Technical fallback: {source_name} consumes {inputs[0]} in the observed trace."
    return f"Technical fallback: {source_name} is present in the traced module hierarchy."


def _semantic_explanation(tag: str, source_name: str, inputs: list[list[int]], outputs: list[list[int]]) -> str:
    descriptions = {
        "input": "Introduces an input representation to the traced model.",
        "embedding_or_projection": "Projects values or channels into another representation width.",
        "position_or_context": "Adds ordering or contextual information to the representation.",
        "attention_or_mixer": "Mixes information between positions or channels.",
        "feed_forward": "Applies a point-wise feed-forward transformation.",
        "normalization_or_residual": "Normalizes, scales, or combines a residual representation.",
        "aggregation_or_decoder": "Aggregates or decodes an intermediate representation.",
        "output_or_head": "Produces an output representation.",
    }
    shape_fact = f" Observed shape: {inputs[0]} → {outputs[0]}." if inputs and outputs else ""
    return f"{descriptions[tag]} Exact source: {source_name}.{shape_fact}"


def _representation(domain: str, tensor: dict[str, Any]) -> str:
    shape = tensor.get("shape") or []
    dtype = str(tensor.get("dtype") or "")
    rank = len(shape)
    if domain == "vision" and rank == 4:
        return "Image-like tensor"
    if domain == "vision" and rank == 3:
        return "Visual token sequence"
    if domain == "audio" and rank >= 3:
        return "Audio feature sequence"
    if domain == "text" and rank == 2 and "int" in dtype:
        return "Token IDs"
    if domain == "text" and rank == 3:
        return "Token representation sequence"
    return f"Rank-{rank} tensor"


def _primary_journey(
    graph: dict[str, Any],
    node_stage: dict[str, str],
    stages_by_id: dict[str, dict[str, Any]],
    domain: str,
) -> list[dict[str, Any]]:
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    tensors = {tensor["tensor_id"]: tensor for tensor in graph.get("tensors", [])}
    order = topological_node_ids(graph)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        outgoing[edge["source"]].append(edge)
    best: dict[str, tuple[tuple[int, int, int], list[dict[str, Any]]]] = {}
    for node_id in order:
        node = nodes[node_id]
        if node.get("kind") == "graph_input":
            best[node_id] = ((4, 0, 0), [])
        if node_id not in best:
            continue
        score, path = best[node_id]
        for edge in outgoing[node_id]:
            confidence = ROUTE_CONFIDENCE.get(edge.get("confidence"), 0)
            candidate_score = (min(score[0], confidence), score[1] + confidence, score[2] + 1)
            target = edge["target"]
            if target not in best or candidate_score > best[target][0]:
                best[target] = (candidate_score, [*path, edge])
    outputs = [node_id for node_id in order if nodes[node_id].get("kind") == "graph_output" and node_id in best]
    if not outputs:
        return []
    target = max(outputs, key=lambda node_id: best[node_id][0])
    path = best[target][1]
    if not path:
        return []
    candidates = [(path[0]["source"], path[0])]
    candidates.extend((edge["target"], edge) for edge in path)
    selected: list[tuple[str, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        node_id, edge = candidate
        tensor = tensors.get(edge["tensor_id"])
        if tensor is None:
            continue
        previous = selected[-1] if selected else None
        changed = bool(previous) and (
            node_stage.get(previous[0]) != node_stage.get(node_id)
            or tensors[previous[1]["tensor_id"]].get("shape") != tensor.get("shape")
        )
        if not previous or changed or index == len(candidates) - 1:
            if previous and previous[1]["tensor_id"] == edge["tensor_id"]:
                selected[-1] = candidate
            else:
                selected.append(candidate)
    if len(selected) < 2:
        selected = [candidates[0], candidates[-1]]
    steps = []
    for index, (node_id, edge) in enumerate(selected):
        tensor = tensors[edge["tensor_id"]]
        node = nodes[node_id]
        previous_shape = steps[-1]["shape"] if steps else None
        shape = list(tensor.get("shape") or [])
        explanation = (
            f"Shape changes from {previous_shape} to {shape}."
            if previous_shape is not None and previous_shape != shape
            else "Shape is preserved at this selected boundary."
        )
        stage_id = node_stage[node_id]
        steps.append({
            "step_id": f"journey-step-{index:03d}",
            "tensor_id": edge["tensor_id"],
            "node_id": node_id,
            "stage_id": stage_id,
            "representation": _representation(domain, tensor),
            "shape": shape,
            "dtype": str(tensor.get("dtype") or "unknown"),
            "transform": "Model input" if index == 0 else node.get("display_name") or node.get("name") or stages_by_id[stage_id]["semantic_name"],
            "explanation": explanation,
            "route_confidence": "exact" if index == 0 else edge.get("confidence", "unresolved"),
        })
    ranks = [ROUTE_CONFIDENCE.get(edge.get("confidence"), 0) for edge in path]
    route_confidence = next(name for name, rank in ROUTE_CONFIDENCE.items() if rank == min(ranks))
    return [{
        "journey_id": "primary-input-output",
        "name": "Primary input-to-output route",
        "input_tensor_id": steps[0]["tensor_id"],
        "output_tensor_ids": [steps[-1]["tensor_id"]],
        "preferred_boundary_tensor_ids": list(dict.fromkeys(step["tensor_id"] for step in steps[1:-1])),
        "route_confidence": route_confidence,
        "steps": steps,
    }]


def _fraction(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def generate_semantics(
    version: dict[str, Any],
    graph: dict[str, Any],
    *,
    generated_at: str,
    config: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    stage_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_registry()
    stage_rules = stage_rules or load_stage_rules()
    config = (config or {}).get("config", config or {})
    domain = _domain(version)
    rule_pack_ids = _matching_rule_packs(domain, config, stage_rules)
    nodes = graph.get("nodes", [])
    nodes_by_id = {node["id"]: node for node in nodes}
    modules = graph.get("modules", [])
    modules_by_id = {module["module_id"]: module for module in modules}
    tag_records = {module["module_id"]: assign_class_tags(module, registry) for module in modules}
    hints = _module_stage_hints(modules, tag_records, stage_rules, rule_pack_ids)
    order = topological_node_ids(graph)
    order_index = {node_id: index for index, node_id in enumerate(order)}

    node_hints: dict[str, tuple[str, int, str]] = {}
    node_segment_keys: dict[str, tuple[str, str]] = {}
    for node_id in order:
        node = nodes_by_id[node_id]
        if node.get("kind") == "graph_input":
            node_hints[node_id] = ("input_adapter", 0, "graph_boundary_rule")
        elif node.get("kind") == "graph_output":
            node_hints[node_id] = ("output_adapter", 0, "graph_boundary_rule")
        else:
            node_hints[node_id] = _effective_stage_hint(node.get("module_id"), modules_by_id, hints)
        anchor = _repeated_anchor(node.get("module_id"), modules_by_id)
        if anchor and node.get("kind") == "aten_op":
            node_hints[node_id] = ("backbone", 1, "traced_repeated_block_rule")
            node_segment_keys[node_id] = ("repeated", str(anchor.get("structural_signature")))
        else:
            node_segment_keys[node_id] = ("stage", node_hints[node_id][0])

    stage_records: list[dict[str, Any]] = []
    node_stage: dict[str, str] = {}
    segment_nodes = [node_id for node_id in order if nodes_by_id[node_id].get("kind") in {"graph_input", "aten_op", "graph_output"}]
    for node_id in segment_nodes:
        stage_type, strength, provenance = node_hints[node_id]
        segment_key = node_segment_keys[node_id]
        current = stage_records[-1] if stage_records else None
        if current is None or current["_segment_key"] != segment_key:
            stage_id = f"stage-{len(stage_records):03d}-{slug(stage_type)}"
            current = {
                "stage_id": stage_id,
                "stage_type": stage_type,
                "semantic_name": STAGE_NAMES[stage_type],
                "what": "",
                "tags": [],
                "module_ids": [],
                "operation_ids": [],
                "entity_ids": [],
                "input_tensor_ids": [],
                "output_tensor_ids": [],
                "input_shapes": [],
                "output_shapes": [],
                "order": len(stage_records),
                "importance": "primary" if stage_type not in {"normalization", "residual_and_scaling", "other"} else "secondary",
                "confidence": "verified_rule" if strength == 0 else "inferred",
                "provenance": [provenance, "trace_topological_order"],
                "module_count": 0,
                "repeated_block_count": 0,
                "parameter_count": 0,
                "operation_count": 0,
                "observed_block_count": 0,
                "template_instance_count": 0,
                "expanded_instances_observed": True,
                "_segment_key": segment_key,
            }
            stage_records.append(current)
        elif strength == 0:
            current["confidence"] = "verified_rule"
            if provenance not in current["provenance"]:
                current["provenance"].insert(0, provenance)
        node_stage[node_id] = current["stage_id"]
        if nodes_by_id[node_id].get("kind") == "aten_op":
            current["operation_ids"].append(node_id)

    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    for edge in graph.get("edges", []):
        outgoing[edge["source"]].append(edge)
        incoming[edge["target"]].append(edge)
    for node_id in order:
        if node_id in node_stage:
            continue
        related = [edge["target"] for edge in outgoing[node_id] if edge["target"] in node_stage]
        related += [edge["source"] for edge in incoming[node_id] if edge["source"] in node_stage]
        if related:
            nearest = min(related, key=lambda other: abs(order_index.get(other, 0) - order_index.get(node_id, 0)))
            node_stage[node_id] = node_stage[nearest]
        else:
            stage_type = node_hints[node_id][0]
            matching = [stage for stage in stage_records if stage["stage_type"] == stage_type]
            node_stage[node_id] = (matching[0] if matching else stage_records[0])["stage_id"]

    stages_by_id = {stage["stage_id"]: stage for stage in stage_records}
    module_stage_counts: dict[str, Counter[str]] = {module["module_id"]: Counter() for module in modules}
    for node_id, stage_id in node_stage.items():
        current = modules_by_id.get(nodes_by_id[node_id].get("module_id") or "")
        while current:
            module_stage_counts[current["module_id"]][stage_id] += 1
            current = modules_by_id.get(current.get("parent_module_id") or "")
    module_stage: dict[str, str] = {}
    for module in modules:
        counts = module_stage_counts[module["module_id"]]
        if counts:
            module_stage[module["module_id"]] = min(
                counts,
                key=lambda stage_id: (-counts[stage_id], stages_by_id[stage_id]["order"]),
            )
        else:
            hint = hints[module["module_id"]][0]
            matching = [stage for stage in stage_records if stage["stage_type"] == hint]
            module_stage[module["module_id"]] = (matching[0] if matching else stage_records[0])["stage_id"]
        stages_by_id[module_stage[module["module_id"]]]["module_ids"].append(module["module_id"])

    entities: dict[str, dict[str, Any]] = {}
    calls_by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in graph.get("module_calls", []):
        calls_by_module[call.get("module_id")].append(call)
    total_entities = len(modules) + len(nodes)
    for module in modules:
        module_id = module["module_id"]
        ports_in = [port for call in calls_by_module[module_id] for port in call.get("input_ports", [])]
        ports_out = [port for call in calls_by_module[module_id] for port in call.get("output_ports", [])]
        input_ids, input_shapes = _unique_ports(ports_in)
        output_ids, output_shapes = _unique_ports(ports_out)
        tags = tag_records[module_id]
        entities[module_id] = {
            "entity_id": module_id,
            "entity_kind": "module",
            "source_name": module.get("display_name") or module.get("class_name") or module_id,
            "semantic_name": TAG_NAMES[tags["primary_tag"]],
            "source_class": module.get("class_name"),
            "qualified_name": module.get("qualified_name"),
            "interface_signature": _interface_text(module),
            "tags": tags["tags"],
            "primary_tag": tags["primary_tag"],
            "stage_id": module_stage[module_id],
            "input_tensor_ids": input_ids,
            "output_tensor_ids": output_ids,
            "input_shapes": input_shapes,
            "output_shapes": output_shapes,
            "what": _semantic_explanation(tags["primary_tag"], module.get("class_name") or module_id, input_shapes, output_shapes) if tags["primary_tag"] != "other" else _technical_explanation(module.get("class_name") or module_id, input_shapes, output_shapes),
            "importance": "primary" if module.get("parent_module_id") is None or module.get("child_module_ids") else "secondary",
            "confidence": tags["confidence"],
            "provenance": tags["provenance"],
            "graph_position": {"order": stages_by_id[module_stage[module_id]]["order"], "total": total_entities},
            "source_ref": module.get("source_ref") or {},
        }
    kind_map = {"aten_op": "operation", "graph_input": "graph_input", "graph_output": "graph_output"}
    for node_id in order:
        node = nodes_by_id[node_id]
        input_ids, input_shapes = _unique_ports(node.get("input_ports", []))
        output_ids, output_shapes = _unique_ports(node.get("output_ports", []))
        if node.get("kind") == "graph_input":
            tags = {"tags": ["input"], "primary_tag": "input", "confidence": "verified_rule", "provenance": ["graph_boundary_rule", "trace"]}
        elif node.get("kind") == "graph_output":
            tags = {"tags": ["output_or_head"], "primary_tag": "output_or_head", "confidence": "verified_rule", "provenance": ["graph_boundary_rule", "trace"]}
        else:
            tags = tag_records.get(node.get("module_id"), {"tags": ["other"], "primary_tag": "other", "confidence": "technical_fallback", "provenance": ["raw_trace_fallback"]})
        source_name = node.get("display_name") or node.get("name") or node_id
        entities[node_id] = {
            "entity_id": node_id,
            "entity_kind": kind_map.get(node.get("kind"), node.get("kind") if node.get("kind") in {"parameter", "buffer", "literal", "unresolved_input"} else "other"),
            "source_name": source_name,
            "semantic_name": TAG_NAMES[tags["primary_tag"]],
            "source_class": modules_by_id.get(node.get("module_id") or "", {}).get("class_name"),
            "qualified_name": node.get("module_path"),
            "interface_signature": node.get("name"),
            "tags": tags["tags"],
            "primary_tag": tags["primary_tag"],
            "stage_id": node_stage[node_id],
            "input_tensor_ids": input_ids,
            "output_tensor_ids": output_ids,
            "input_shapes": input_shapes,
            "output_shapes": output_shapes,
            "what": _semantic_explanation(tags["primary_tag"], source_name, input_shapes, output_shapes) if tags["primary_tag"] != "other" else _technical_explanation(source_name, input_shapes, output_shapes),
            "importance": "primary" if node.get("kind") in {"graph_input", "graph_output"} else "implementation_detail" if node.get("kind") == "aten_op" else "secondary",
            "confidence": tags["confidence"],
            "provenance": tags["provenance"],
            "graph_position": {"order": order_index[node_id], "total": total_entities},
            "source_ref": node.get("source_ref") or {},
        }

    for entity_id, entity in entities.items():
        stages_by_id[entity["stage_id"]]["entity_ids"].append(entity_id)
    for stage in stage_records:
        stage["module_ids"] = list(dict.fromkeys(stage["module_ids"]))
        stage["module_count"] = len(stage["module_ids"])
        signatures = Counter(modules_by_id[module_id].get("structural_signature") for module_id in stage["module_ids"])
        stage["repeated_block_count"] = sum(count for signature, count in signatures.items() if signature and count > 1)
        if stage["_segment_key"][0] == "repeated":
            repeated_signature = stage["_segment_key"][1]
            anchor_modules = [
                modules_by_id[module_id]
                for module_id in stage["module_ids"]
                if modules_by_id[module_id].get("structural_signature") == repeated_signature
            ]
            observed_paths = {module.get("qualified_name") for module in anchor_modules}
            stage["observed_block_count"] = len(observed_paths)
            stage["repeated_block_count"] = len(observed_paths)
            for template in version.get("trace_templates", []):
                if observed_paths & set(template.get("observed_module_paths", [])):
                    stage["template_instance_count"] = max(stage["template_instance_count"], len(template.get("instance_module_paths", [])))
                    stage["expanded_instances_observed"] = bool(template.get("expanded_instances_observed"))
            stage["template_instance_count"] = stage["template_instance_count"] or stage["observed_block_count"]
        else:
            stage["observed_block_count"] = stage["repeated_block_count"]
            stage["template_instance_count"] = stage["repeated_block_count"]
        tags = [entities[entity_id]["primary_tag"] for entity_id in stage["entity_ids"]]
        stage["tags"] = list(dict.fromkeys(tag for tag in tags if tag != "other")) or ["other"]
        stage["operation_count"] = len(stage["operation_ids"])
        stage["what"] = (
            f"{stage['semantic_name']} contains {stage['module_count']} source modules and "
            f"{stage['operation_count']} observed operations in this trace."
        )
        del stage["_segment_key"]

    edge_groups: dict[tuple[str, str], dict[str, Any]] = {}
    confidence_order = ["exact", "lineage", "inferred", "ambiguous", "unresolved"]
    for edge in graph.get("edges", []):
        source_stage, target_stage = node_stage[edge["source"]], node_stage[edge["target"]]
        if source_stage == target_stage:
            continue
        key = (source_stage, target_stage)
        record = edge_groups.setdefault(key, {"source_stage_id": source_stage, "target_stage_id": target_stage, "tensor_ids": [], "confidence": edge.get("confidence", "unresolved")})
        if edge["tensor_id"] not in record["tensor_ids"]:
            record["tensor_ids"].append(edge["tensor_id"])
        if confidence_order.index(edge.get("confidence", "unresolved")) > confidence_order.index(record["confidence"]):
            record["confidence"] = edge.get("confidence", "unresolved")
        source = stages_by_id[source_stage]
        target = stages_by_id[target_stage]
        if edge["tensor_id"] not in source["output_tensor_ids"]:
            source["output_tensor_ids"].append(edge["tensor_id"])
            source["output_shapes"].append(list(edge.get("shape") or []))
        if edge["tensor_id"] not in target["input_tensor_ids"]:
            target["input_tensor_ids"].append(edge["tensor_id"])
            target["input_shapes"].append(list(edge.get("shape") or []))

    trace_parameter_total = int((version.get("parameters") or {}).get("total") or 0)
    parameter_by_stage: Counter[str] = Counter()
    canonical_seen: set[str] = set()
    has_canonical_ids = any(item.get("parameter_id") for module in modules for item in module.get("parameters", []))
    if has_canonical_ids:
        for module in modules:
            for parameter in module.get("parameters", []):
                parameter_id = parameter.get("parameter_id")
                if not parameter_id or parameter_id in canonical_seen:
                    continue
                canonical_seen.add(parameter_id)
                parameter_by_stage[module_stage[module["module_id"]]] += int(parameter.get("numel") or _shape_product(parameter.get("shape") or []))
    else:
        tensors = {tensor["tensor_id"]: tensor for tensor in graph.get("tensors", [])}
        for node in nodes:
            if node.get("kind") != "parameter" or not node.get("output_ports"):
                continue
            tensor_id = node["output_ports"][0].get("tensor_id")
            if tensor_id in canonical_seen or tensor_id not in tensors:
                continue
            canonical_seen.add(tensor_id)
            parameter_by_stage[node_stage[node["id"]]] += _shape_product(tensors[tensor_id].get("shape") or [])
    mapped_parameter_total = min(sum(parameter_by_stage.values()), trace_parameter_total)
    if sum(parameter_by_stage.values()) > trace_parameter_total:
        remaining = trace_parameter_total
        for stage in stage_records:
            value = min(parameter_by_stage[stage["stage_id"]], remaining)
            parameter_by_stage[stage["stage_id"]] = value
            remaining -= value
    for stage in stage_records:
        stage["parameter_count"] = parameter_by_stage[stage["stage_id"]]

    operation_total = len([node for node in nodes if node.get("kind") == "aten_op"])
    unclassified_parameters = max(0, trace_parameter_total - sum(parameter_by_stage.values()))
    parameter_distribution = [
        {"stage_id": stage["stage_id"], "value": stage["parameter_count"], "percentage": _fraction(stage["parameter_count"], trace_parameter_total)}
        for stage in stage_records if stage["parameter_count"]
    ]
    if unclassified_parameters or not parameter_distribution:
        parameter_distribution.append({"stage_id": "unclassified", "value": unclassified_parameters, "percentage": _fraction(unclassified_parameters, trace_parameter_total)})
    operation_distribution = [
        {"stage_id": stage["stage_id"], "value": stage["operation_count"], "percentage": _fraction(stage["operation_count"], operation_total)}
        for stage in stage_records if stage["operation_count"]
    ] or [{"stage_id": "unclassified", "value": 0, "percentage": 0.0}]

    semantic = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "version_id": version["version_id"],
        "generated_at": generated_at,
        "generator_version": SEMANTIC_GENERATOR_VERSION,
        "class_tag_vocab_version": TAG_VOCAB_VERSION,
        "domain": domain,
        "task": str(version.get("task_type") or "other"),
        "rule_pack_ids": rule_pack_ids,
        "stages": stage_records,
        "stage_edges": list(edge_groups.values()),
        "entities": entities,
        "journeys": _primary_journey(graph, node_stage, stages_by_id, domain),
        "metrics": {
            "trace_parameter_total": trace_parameter_total,
            "official_parameter_estimate": (version.get("resource_preflight") or {}).get("estimated_parameter_count"),
            "trace_operation_total": operation_total,
            "parameter_distribution": parameter_distribution,
            "operation_distribution": operation_distribution,
        },
        "coverage": {
            "module_stage_fraction": _fraction(sum(module_stage[module["module_id"]] in stages_by_id for module in modules), len(modules)),
            "class_tag_fraction": _fraction(sum(tag_records[module["module_id"]]["primary_tag"] != "other" for module in modules), len(modules)),
            "parameter_stage_fraction": _fraction(sum(parameter_by_stage.values()), trace_parameter_total),
            "operation_stage_fraction": _fraction(sum(stage["operation_count"] for stage in stage_records if stage["stage_type"] != "other"), operation_total),
            "parameter_accounted_fraction": _fraction(sum(item["value"] for item in parameter_distribution), trace_parameter_total),
            "operation_accounted_fraction": _fraction(sum(item["value"] for item in operation_distribution), operation_total),
            "verified_module_fraction": _fraction(sum(tag_records[module["module_id"]]["confidence"] == "verified_rule" for module in modules), len(modules)),
        },
    }
    validation_errors = sorted(Draft202012Validator(read_json(SCHEMA_ROOT / "semantic-model.v1.schema.json")).iter_errors(semantic), key=lambda error: list(error.path))
    if validation_errors:
        raise ValueError("generated semantic asset is invalid: " + "; ".join(error.message for error in validation_errors[:10]))
    return semantic


def semantic_index_entry(
    semantic: dict[str, Any],
    semantic_ref: str,
    *,
    version_status: str = "passed",
) -> dict[str, Any]:
    has_fallback = any(
        entity.get("confidence") == "technical_fallback" or entity.get("primary_tag") == "other"
        for entity in semantic.get("entities", {}).values()
    )
    generation_status = "partial" if version_status == "partial" else "fallback" if has_fallback else "passed"
    return {
        "version_id": semantic["version_id"],
        "semantic_ref": semantic_ref,
        "domain": semantic["domain"],
        "stage_count": len(semantic["stages"]),
        "generation_status": generation_status,
        "coverage": semantic["coverage"],
    }


def publish_semantic_contracts(model_code: Path) -> dict[str, str]:
    write_json(model_code / SEMANTIC_SCHEMA_REF, read_json(SCHEMA_ROOT / "semantic-model.v1.schema.json"))
    write_json(model_code / INTERFACE_TAGS_REF, load_registry())
    return {
        "semantic_schema_ref": SEMANTIC_SCHEMA_REF,
        "interface_tags_ref": INTERFACE_TAGS_REF,
    }


def semantic_index_document(entries: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generator_version": SEMANTIC_GENERATOR_VERSION,
        "class_tag_vocab_version": TAG_VOCAB_VERSION,
        "semantic_schema_ref": SEMANTIC_SCHEMA_REF,
        "interface_tags_ref": INTERFACE_TAGS_REF,
        "report_ref": SEMANTIC_REPORT_REF,
        "versions": entries,
    }


def semantic_report_document(
    entries: list[dict[str, Any]],
    *,
    generated_at: str,
    catalog_family_count: int,
    catalog_version_count: int,
    selected_family_count: int,
    selected_version_count: int,
    generated_family_count: int,
    failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    failures = failures or []
    counts = Counter(entry["generation_status"] for entry in entries)
    counts["failed"] = len(failures)
    generated_version_count = len(entries)
    unselected_family_count = max(0, catalog_family_count - selected_family_count)
    unselected_version_count = max(0, catalog_version_count - selected_version_count)
    failed_selected_family_count = max(0, selected_family_count - generated_family_count)
    failed_selected_count = max(0, selected_version_count - generated_version_count)
    reasons = []
    if unselected_family_count or unselected_version_count:
        reasons.append({
            "reason": "outside_selected_build_scope",
            "family_count": unselected_family_count,
            "version_count": unselected_version_count,
        })
    if failed_selected_family_count or failed_selected_count:
        reasons.append({
            "reason": "build_failed",
            "family_count": failed_selected_family_count,
            "version_count": failed_selected_count,
        })
    models = [{
        "version_id": entry["version_id"],
        "status": entry["generation_status"],
        "semantic_ref": entry["semantic_ref"],
        "coverage": entry["coverage"],
        "reason": {
            "passed": "validated_without_technical_fallback",
            "fallback": "validated_with_technical_fallback",
            "partial": "validated_from_partial_technical_record",
        }[entry["generation_status"]],
    } for entry in entries]
    models.extend({
        "version_id": str(failure.get("version_id") or "unknown"),
        "status": "failed",
        "semantic_ref": None,
        "coverage": None,
        "reason": str(failure.get("error_type") or "build_failed"),
    } for failure in failures)
    return {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generator_version": SEMANTIC_GENERATOR_VERSION,
        "catalog": {
            "family_count": catalog_family_count,
            "normalized_version_count": catalog_version_count,
            "selected_family_count": selected_family_count,
            "selected_version_count": selected_version_count,
            "generated_family_count": generated_family_count,
            "generated_version_count": generated_version_count,
            "generated_family_fraction": round(generated_family_count / catalog_family_count, 6) if catalog_family_count else 1.0,
            "generated_version_fraction": round(generated_version_count / catalog_version_count, 6) if catalog_version_count else 1.0,
        },
        "counts": {name: int(counts[name]) for name in ("passed", "fallback", "partial", "failed")},
        "remaining_reasons": reasons,
        "models": models,
        "failures": [{
            "version_id": str(failure.get("version_id") or "unknown"),
            "error_type": str(failure.get("error_type") or "unknown"),
            "message": str(failure.get("message") or ""),
        } for failure in failures],
    }


def materialize_semantic(
    model_code: Path,
    version: dict[str, Any],
    *,
    generated_at: str,
    registry: dict[str, Any] | None = None,
    stage_rules: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    graph = read_json(model_code / version["graph_ref"])
    config = read_json(model_code / version["trace_config_ref"]) if version.get("trace_config_ref") else read_json(model_code / version["config_ref"])
    semantic = generate_semantics(version, graph, generated_at=generated_at, config=config, registry=registry, stage_rules=stage_rules)
    semantic_ref = f"semantics/{version['version_id']}.json"
    write_json(model_code / semantic_ref, semantic)
    return semantic, semantic_ref


def materialize_catalog(model_code: Path) -> dict[str, Any]:
    manifest_path = model_code / "manifest.v2.json"
    manifest = read_json(manifest_path)
    generated_at = manifest.get("semantic_generated_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    registry, stage_rules = load_registry(), load_stage_rules()
    publish_semantic_contracts(model_code)
    entries = []
    for version_id in manifest["versions"]:
        version_path = model_code / "versions" / f"{version_id}.json"
        version = read_json(version_path)
        semantic, semantic_ref = materialize_semantic(model_code, version, generated_at=generated_at, registry=registry, stage_rules=stage_rules)
        version["semantic_ref"] = semantic_ref
        version["artifact_refs"] = sorted(set([*version.get("artifact_refs", []), semantic_ref]))
        write_json(version_path, version)
        entries.append(semantic_index_entry(semantic, semantic_ref, version_status=version.get("status", "passed")))
    index = semantic_index_document(entries, generated_at)
    semantic_index_ref = "indexes/semantic.v1.json"
    write_json(model_code / semantic_index_ref, index)
    build_report = read_json(model_code / manifest["build_report"])
    report = semantic_report_document(
        entries,
        generated_at=generated_at,
        catalog_family_count=int(build_report.get("catalog_model_count") or len(manifest.get("families", []))),
        catalog_version_count=int(build_report.get("normalized_version_count") or len(manifest.get("versions", []))),
        selected_family_count=len(manifest.get("families", [])),
        selected_version_count=int(build_report.get("selected_version_count") or len(manifest.get("versions", []))),
        generated_family_count=len(manifest.get("families", [])),
        failures=build_report.get("failures", []),
    )
    write_json(model_code / SEMANTIC_REPORT_REF, report)
    build_report["semantic_generation"] = {
        "report_ref": SEMANTIC_REPORT_REF,
        "generator_version": SEMANTIC_GENERATOR_VERSION,
        "generated_at": generated_at,
        "counts": report["counts"],
        "catalog": report["catalog"],
    }
    write_json(model_code / manifest["build_report"], build_report)
    manifest["semantic_index"] = semantic_index_ref
    manifest["semantic_report"] = SEMANTIC_REPORT_REF
    manifest["semantic_generated_at"] = generated_at
    manifest["semantic_generator_version"] = SEMANTIC_GENERATOR_VERSION
    manifest["semantic_contracts"] = {
        "schema_ref": SEMANTIC_SCHEMA_REF,
        "interface_tags_ref": INTERFACE_TAGS_REF,
    }
    write_json(model_code / manifest["asset_index"], sorted(path.relative_to(model_code).as_posix() for path in model_code.rglob("*") if path.is_file() and path.relative_to(model_code).as_posix() != manifest["asset_index"]))
    files = [path for path in model_code.rglob("*") if path.is_file()]
    manifest["cloudflare_pages_check"] = {
        "file_count": len(files),
        "max_file_size_bytes": max((path.stat().st_size for path in files), default=0),
        "passed": len(files) <= 20_000 and max((path.stat().st_size for path in files), default=0) <= 25 * 1024 * 1024,
    }
    write_json(manifest_path, manifest)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic cross-domain semantic assets")
    parser.add_argument("--model-code", type=Path, default=Path("model_code"))
    args = parser.parse_args()
    index = materialize_catalog(args.model_code)
    print(f"generated semantic assets for {len(index['versions'])} versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
