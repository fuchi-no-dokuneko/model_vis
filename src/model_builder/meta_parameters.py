"""Inspect parameter identities and task wrappers without tensor allocation."""
from copy import deepcopy
from importlib import import_module

import torch


def model_parameter_facts(class_path, raw_config, arguments=None):
    module, name = class_path.rsplit(".", 1)
    cls = getattr(import_module(module), name)
    config = cls.config_class.from_dict(deepcopy(raw_config))
    with torch.device("meta"):
        model = cls(config, **(arguments or {}))
        model.tie_weights()
    base = model.base_model
    wrapped = base is not model
    return {
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "head_scope_kind": "task_wrapper" if wrapped else "direct_entrypoint",
        "head_scope": f"Task wrapper {name} around {type(base).__name__}" if wrapped
        else f"Direct entrypoint {name}; no separate task wrapper",
    }


def count_parameters(class_path, raw_config, arguments=None):
    return model_parameter_facts(class_path, raw_config, arguments)["parameter_count"]
