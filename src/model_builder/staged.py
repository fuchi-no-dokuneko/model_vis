from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any


GIB = 1024 ** 3
SCHEDULE_FIELDS = (
    "layers_block_type", "layer_types", "mlp_layer_types", "indexer_types",
    "attention_types", "block_types",
)


def host_resources() -> dict[str, int]:
    total = 0
    available = 0
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, raw = line.split(":", 1)
            values[name] = int(raw.strip().split()[0]) * 1024
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
    except (OSError, ValueError):
        if hasattr(os, "sysconf"):
            total = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
            available = total
    return {
        "total_memory_bytes": total,
        "available_memory_bytes": available,
        "cpu_count": os.cpu_count() or 1,
    }


def _integer(config: dict[str, Any], *names: str, default: int = 0) -> int:
    for name in names:
        value = config.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return default


def estimate_parameter_count(config: dict[str, Any]) -> int:
    hidden = _integer(config, "hidden_size", "d_model", "dim", "embed_dim")
    layers = _integer(config, "num_hidden_layers", "n_layer", "num_layers", default=1)
    vocab = _integer(config, "vocab_size")
    intermediate = _integer(config, "intermediate_size", "ffn_dim", "ffn_hidden_size", default=hidden * 4)
    heads = max(1, _integer(config, "num_attention_heads", "num_heads", "n_head", default=1))
    kv_heads = _integer(config, "num_key_value_heads", default=heads)
    embeddings = vocab * hidden
    attention = hidden * hidden * (2 + (2 * kv_heads / heads))
    dense_mlp = 3 * hidden * intermediate
    first_dense = min(layers, _integer(config, "first_k_dense_replace", default=layers))
    experts = _integer(config, "n_routed_experts", "num_local_experts", "num_experts")
    moe_width = _integer(config, "moe_intermediate_size", default=intermediate)
    shared = _integer(config, "n_shared_experts")
    moe_mlp = 3 * hidden * moe_width * (experts + shared) if experts else dense_mlp
    core = int(embeddings + first_dense * (attention + dense_mlp) + (layers - first_dense) * (attention + moe_mlp))
    nested = sum(
        estimate_parameter_count(value)
        for key, value in config.items()
        if key.endswith("_config") and isinstance(value, dict)
    )
    return max(core + nested, hidden * hidden * max(1, layers))


def detect_layer_variants(config: dict[str, Any]) -> list[dict[str, Any]]:
    layer_count = _integer(config, "num_hidden_layers", "n_layer", "num_layers", default=1)
    schedules = {
        name: value
        for name in SCHEDULE_FIELDS
        if isinstance((value := config.get(name)), list) and len(value) >= layer_count
    }
    first_dense = _integer(config, "first_k_dense_replace", default=layer_count)
    moe_frequency = max(1, _integer(config, "moe_layer_freq", default=1))
    has_experts = _integer(config, "n_routed_experts", "num_local_experts", "num_experts") > 0
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for index in range(layer_count):
        effective = {name: values[index] for name, values in schedules.items()}
        if has_experts:
            effective["feed_forward_role"] = (
                "dense" if index < first_dense or (index - first_dense) % moe_frequency else "moe"
            )
        signature = json.dumps(effective, sort_keys=True, separators=(",", ":"))
        if signature not in grouped:
            grouped[signature] = {
                "template_id": f"layer-template-{len(grouped):03d}",
                "representative_layer_index": index,
                "effective_config": effective,
                "layer_indices": [],
            }
        grouped[signature]["layer_indices"].append(index)
    return list(grouped.values())


def plan_trace(config: dict[str, Any] | None, resources: dict[str, int] | None = None) -> dict[str, Any]:
    resources = resources or host_resources()
    if config is None:
        return {
            "execution_mode": "unique_structure_forward",
            "decision": "official_config_unavailable",
            "resource_preflight": resources,
            "estimated_parameter_count": None,
            "estimated_peak_bytes": None,
            "resource_budget_bytes": int(resources["available_memory_bytes"] * 0.65),
            "templates": [{
                "template_id": "layer-template-000",
                "representative_layer_index": 0,
                "effective_config": {},
                "layer_indices": [0],
            }],
            "compact_schedule": {},
        }
    estimate = estimate_parameter_count(config)
    parameter_bytes = estimate * 4
    estimated_peak = parameter_bytes * 6
    budget = int(resources["available_memory_bytes"] * 0.65)
    templates = detect_layer_variants(config)
    native_schema = not config.get("model_type") and config.get("ssm_cfg", {}).get("layer") == "Mamba2"
    full = estimated_peak <= budget and not native_schema
    compact_schedule = {
        field: [template["effective_config"][field] for template in templates]
        for field in SCHEDULE_FIELDS
        if all(field in template["effective_config"] for template in templates)
    }
    return {
        "execution_mode": "full_model_forward" if full else "unique_structure_forward",
        "decision": (
            "official_model_fits_host" if full
            else "native_config_requires_adapter" if native_schema
            else "official_model_exceeds_host"
        ),
        "resource_preflight": resources,
        "estimated_parameter_count": estimate,
        "estimated_parameter_bytes": parameter_bytes,
        "estimated_peak_bytes": estimated_peak,
        "resource_budget_bytes": budget,
        "templates": templates,
        "compact_schedule": compact_schedule,
    }


def apply_compact_schedule(config: Any, plan: dict[str, Any]) -> Any:
    templates = plan.get("templates", [])
    layer_count = max(1, len(templates))
    for name in ("num_hidden_layers", "n_layer", "num_layers"):
        if hasattr(config, name):
            setattr(config, name, layer_count)
    for name, values in plan.get("compact_schedule", {}).items():
        if hasattr(config, name):
            current = getattr(config, name)
            setattr(config, name, tuple(values) if isinstance(current, tuple) else list(values))
    roles = [template["effective_config"].get("feed_forward_role") for template in templates]
    if "dense" in roles and "moe" in roles:
        if hasattr(config, "first_k_dense_replace"):
            config.first_k_dense_replace = roles.index("moe")
        if hasattr(config, "moe_layer_freq"):
            config.moe_layer_freq = 1
    if getattr(config, "model_type", None) == "zamba2" and hasattr(config, "layers_block_type"):
        config.hybrid_layer_ids = [
            index for index, block_type in enumerate(config.layers_block_type)
            if block_type == "hybrid"
        ]
    return config


def attach_template_provenance(trace: dict[str, Any], plan: dict[str, Any]) -> None:
    groups = trace.get("graph", {}).get("layer_groups", [])
    templates = []
    template_by_group: dict[str, str] = {}
    for index, template in enumerate(plan.get("templates", [])):
        full_forward = plan["execution_mode"] == "full_model_forward"
        observed_groups = (
            [groups[layer_index] for layer_index in template["layer_indices"] if layer_index < len(groups)]
            if full_forward else [groups[index]] if index < len(groups) else []
        )
        group = observed_groups[0] if observed_groups else None
        observed_path = group.get("qualified_name") if group else None
        instance_paths = [value["qualified_name"] for value in observed_groups]
        if not full_forward:
            instance_paths = []
            for layer_index in template["layer_indices"]:
                if observed_path:
                    instance_paths.append(re.sub(r"(?<=\.)\d+(?=\.|$)", str(layer_index), observed_path, count=1))
                else:
                    instance_paths.append(f"layers.{layer_index}")
        record = {
            **template,
            "observed_module_path": observed_path,
            "observed_module_paths": [value["qualified_name"] for value in observed_groups],
            "instance_module_paths": instance_paths,
            "provenance": "full_runtime_forward" if full_forward else "representative_runtime_forward",
            "expanded_instances_observed": full_forward,
        }
        templates.append(record)
        for observed_group in observed_groups:
            template_by_group[observed_group["layer_group_id"]] = template["template_id"]
            observed_group["template_id"] = template["template_id"]
    for node in trace.get("graph", {}).get("nodes", []):
        if node.get("layer_group_id") in template_by_group:
            node["template_id"] = template_by_group[node["layer_group_id"]]
    trace["execution_mode"] = plan["execution_mode"]
    trace["resource_preflight"] = plan
    trace["trace_templates"] = templates
    trace["graph"]["trace_templates"] = templates
    trace["graph"]["resource_preflight"] = plan
