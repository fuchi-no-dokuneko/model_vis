"""Count initialized parameter identities without allocating model tensors."""
from importlib import import_module
from copy import deepcopy

import torch

from .util import read_json


def _count(class_path, raw_config, arguments=None):
    module, name = class_path.rsplit(".", 1)
    cls = getattr(import_module(module), name)
    config = cls.config_class.from_dict(deepcopy(raw_config))
    with torch.device("meta"):
        model = cls(config, **(arguments or {}))
        model.tie_weights()
    return sum(parameter.numel() for parameter in model.parameters())


def parameter_evidence(model_code, version, graph):
    root = next((m for m in graph["modules"] if not m.get("parent_module_id")), {})
    class_path = root.get("class_name", "")
    evidence = {
        "model_class": class_path,
        "parameter_count": None,
        "basis": "Config-derived; unique parameter identities on a meta device",
        "head_scope": "Executed entrypoint; task heads only when included by this class",
        "publisher_parameter_count": None,
        "variants": [],
        "status": "unavailable",
    }
    if not version.get("official_config_ref") or not version.get("official_config_source"):
        evidence["reason"] = "No pinned configuration for the selected model"
        return evidence
    source = version["official_config_source"]
    evidence.update(checkpoint=source["repo_id"], revision=source["revision"])
    config = read_json(model_code / version["official_config_ref"])
    arguments = {
        item["name"]: item["value"]
        for item in root.get("constructor", {}).get("effective_arguments", [])
        if item["name"] != "config" and isinstance(item.get("value"), (bool, int, float, str))
    }
    try:
        evidence["parameter_count"] = _count(class_path, config, arguments)
        evidence["status"] = "config_derived"
    except (ValueError, TypeError, RuntimeError, AttributeError, ImportError, KeyError, NotImplementedError) as error:
        evidence["reason"] = f"Exact entrypoint count unavailable: {type(error).__name__}"
    for name in config.get("architectures", []):
        if name == class_path.rsplit(".", 1)[-1]:
            continue
        try:
            count = _count(f"transformers.{name}", config)
        except (ValueError, TypeError, RuntimeError, AttributeError, ImportError, KeyError, NotImplementedError):
            continue
        evidence["variants"].append({"model_class": name, "parameter_count": count,
                                     "head_scope": "Pinned config architecture, including its task head"})
    return evidence
