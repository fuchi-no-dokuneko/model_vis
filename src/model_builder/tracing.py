from __future__ import annotations

import hashlib
import inspect
import sys
from collections import defaultdict
from contextlib import AbstractContextManager
from pathlib import Path
from types import FrameType
from typing import Any, Callable, Iterable

import torch
from torch import nn
from torch.utils._python_dispatch import TorchDispatchMode

from . import SCHEMA_VERSION
from .introspection import (
    normalized_source_path,
    sanitize_runtime_value,
    source_ref,
    source_ref_from_frame,
    tensor_metadata,
)
from .util import sha256_json


def _flatten_named(value: Any, path: str) -> list[tuple[str, torch.Tensor]]:
    if torch.is_tensor(value):
        return [(path, value)]
    result: list[tuple[str, torch.Tensor]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            result.extend(_flatten_named(item, child))
    elif isinstance(value, tuple) and hasattr(value, "_fields"):
        for key, item in zip(value._fields, value, strict=False):
            child = f"{path}.{key}" if path else str(key)
            result.extend(_flatten_named(item, child))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            result.extend(_flatten_named(item, f"{path}[{index}]"))
    elif hasattr(value, "to_tuple"):
        result.extend(_flatten_named(value.to_tuple(), path))
    return result


def _bound_values(callable_obj: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
        bound = signature.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except (TypeError, ValueError):
        return {
            **{f"arg[{index}]": value for index, value in enumerate(args)},
            **kwargs,
        }


def _binding_metadata(
    callable_obj: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return {
            **{
                f"arg[{index}]": {
                    "argument_kind": "positional",
                    "required": True,
                    "optional": False,
                    "supplied_by": "positional",
                    "position": index,
                    "keyword_name": None,
                }
                for index in range(len(args))
            },
            **{
                name: {
                    "argument_kind": "keyword",
                    "required": True,
                    "optional": False,
                    "supplied_by": "keyword",
                    "position": None,
                    "keyword_name": name,
                }
                for name in kwargs
            },
        }
    positional_names: dict[str, int] = {}
    remaining = len(args)
    position = 0
    for parameter in signature.parameters.values():
        if remaining <= 0:
            break
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD):
            positional_names[parameter.name] = position
            remaining -= 1
            position += 1
        elif parameter.kind == parameter.VAR_POSITIONAL:
            positional_names[parameter.name] = position
            remaining = 0
    result = {}
    for parameter in signature.parameters.values():
        required = (
            parameter.default is inspect.Parameter.empty
            and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        )
        if parameter.name in positional_names:
            supplied_by = "positional"
        elif parameter.name in kwargs:
            supplied_by = "keyword"
        else:
            supplied_by = "default"
        result[parameter.name] = {
            "argument_kind": parameter.kind.name.lower(),
            "required": required,
            "optional": not required,
            "supplied_by": supplied_by,
            "position": positional_names.get(parameter.name),
            "keyword_name": parameter.name if supplied_by == "keyword" else None,
        }
    return result


def _named_call_tensors(
    callable_obj: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> list[tuple[str, torch.Tensor, dict[str, Any]]]:
    result: list[tuple[str, torch.Tensor, dict[str, Any]]] = []
    bindings = _binding_metadata(callable_obj, args, kwargs)
    for name, value in _bound_values(callable_obj, args, kwargs).items():
        result.extend(
            (path, tensor, bindings.get(name, {}))
            for path, tensor in _flatten_named(value, name)
        )
    return result


def _named_outputs(value: Any) -> list[tuple[str, torch.Tensor]]:
    if torch.is_tensor(value):
        return [("output", value)]
    return _flatten_named(value, "output")


def _non_tensor_arguments(
    values: dict[str, Any],
    bindings: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for name, value in values.items():
        if _flatten_named(value, name):
            continue
        result.append({
            "name": name,
            "value": sanitize_runtime_value(value),
            **(bindings or {}).get(name, {}),
        })
    return result


class LineRecorder(AbstractContextManager["LineRecorder"]):
    def __init__(self, package_roots: tuple[Path, ...]) -> None:
        self.package_prefixes = tuple(f"{path.resolve().as_posix()}/" for path in package_roots)
        self.lines: dict[str, set[int]] = defaultdict(set)

    def _trace(self, frame: FrameType, event: str, arg: Any) -> Callable[..., Any] | None:
        if event == "line" and frame.f_code.co_filename.startswith(self.package_prefixes):
            path = normalized_source_path(frame.f_code.co_filename)
            if path:
                self.lines[path].add(frame.f_lineno)
        return self._trace

    def __enter__(self) -> LineRecorder:
        sys.settrace(self._trace)
        return self

    def __exit__(self, *exc: object) -> None:
        sys.settrace(None)


def _structural_signature(module: nn.Module) -> str:
    child_tree = [
        (name, f"{type(child).__module__}.{type(child).__qualname__}")
        for name, child in module.named_modules()
    ]
    parameters = sorted((name, list(value.shape)) for name, value in module.named_parameters(recurse=True))
    buffers = sorted((name, list(value.shape)) for name, value in module.named_buffers(recurse=True))
    return "structure.sha256." + sha256_json({
        "class": f"{type(module).__module__}.{type(module).__qualname__}",
        "children": child_tree,
        "parameters": parameters,
        "buffers": buffers,
    })


def _module_records(
    model: nn.Module,
    constructors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, str], dict[str, str]]:
    constructor_by_path = {item["qualified_name"]: item for item in constructors}
    named = list(model.named_modules())
    id_by_object = {id(module): f"module-{index:05d}" for index, (_, module) in enumerate(named)}
    path_by_object = {id(module): path or "<root>" for path, module in named}
    records = []
    for index, (path, module) in enumerate(named):
        qualified = path or "<root>"
        parent_path = path.rsplit(".", 1)[0] if "." in path else ("<root>" if path else None)
        parent = model.get_submodule(parent_path) if parent_path not in {None, "<root>"} else (model if path else None)
        record = {
            "module_id": id_by_object[id(module)],
            "qualified_name": qualified,
            "display_name": type(module).__name__,
            "class_name": f"{type(module).__module__}.{type(module).__qualname__}",
            "parent_module_id": id_by_object.get(id(parent)) if parent is not None else None,
            "child_module_ids": [],
            "source_ref": source_ref(type(module).forward),
            "constructor": constructor_by_path.get(qualified, {}),
            "parameters": [{
                "name": name,
                **tensor_metadata(value),
                "trainable": bool(value.requires_grad),
            } for name, value in module.named_parameters(recurse=False)],
            "buffers": [{"name": name, **tensor_metadata(value)} for name, value in module.named_buffers(recurse=False)],
            "structural_signature": _structural_signature(module),
            "layer_group_id": None,
            "call_ids": [],
        }
        records.append(record)
    by_id = {item["module_id"]: item for item in records}
    for item in records:
        parent_id = item["parent_module_id"]
        if parent_id:
            by_id[parent_id]["child_module_ids"].append(item["module_id"])
    return records, id_by_object, path_by_object


def _assign_layer_groups(
    model: nn.Module,
    modules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    by_id = {item["module_id"]: item for item in modules}
    module_by_path = {path or "<root>": module for path, module in model.named_modules()}
    candidates: set[str] = set()
    children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in modules:
        if item["parent_module_id"]:
            children_by_parent[item["parent_module_id"]].append(item)
    for parent_id, children in children_by_parent.items():
        parent = module_by_path[by_id[parent_id]["qualified_name"]]
        if isinstance(parent, nn.ModuleList):
            candidates.update(item["module_id"] for item in children)
            continue
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for child in children:
            grouped[child["structural_signature"]].append(child)
        for values in grouped.values():
            if len(values) < 2:
                continue
            class_name = values[0]["display_name"].lower()
            if any(token in class_name for token in ("layer", "block", "stage", "expert")):
                candidates.update(item["module_id"] for item in values)
    groups = []
    group_by_module: dict[str, str] = {}
    for item in modules:
        if item["module_id"] not in candidates:
            continue
        group_id = f"layer-{len(groups):05d}"
        group_by_module[item["module_id"]] = group_id
        groups.append({
            "layer_group_id": group_id,
            "module_id": item["module_id"],
            "qualified_name": item["qualified_name"],
            "display_name": item["display_name"],
            "structural_signature": item["structural_signature"],
            "color_index": len(groups),
        })

    group_for_path: dict[str, str | None] = {}
    for item in modules:
        current: dict[str, Any] | None = item
        group_id = None
        while current:
            if current["module_id"] in group_by_module:
                group_id = group_by_module[current["module_id"]]
                break
            parent_id = current["parent_module_id"]
            current = by_id.get(parent_id) if parent_id else None
        item["layer_group_id"] = group_id
        group_for_path[item["qualified_name"]] = group_id
    return groups, group_for_path


class RuntimeGraphRecorder(TorchDispatchMode):
    def __init__(
        self,
        version_id: str,
        model: nn.Module,
        modules: list[dict[str, Any]],
        module_ids: dict[int, str],
        module_paths: dict[int, str],
        layer_for_path: dict[str, str | None],
    ) -> None:
        super().__init__()
        self.version_id = version_id
        self.model = model
        self.modules = modules
        self.module_ids = module_ids
        self.module_paths = module_paths
        self.layer_for_path = layer_for_path
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.tensors: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.call_stack: list[str] = []
        self._call_by_id: dict[str, dict[str, Any]] = {}
        self._module_by_id = {item["module_id"]: item for item in modules}
        self._tensor_id_by_object: dict[int, str] = {}
        self._storage_id_by_runtime_key: dict[tuple[str, int, int], str] = {}
        self._tensor_refs: dict[str, torch.Tensor] = {}
        self._tensor_by_id: dict[str, dict[str, Any]] = {}
        self._producer_by_tensor: dict[str, tuple[str, str]] = {}
        self._producer_by_storage: dict[str, tuple[str, str, str]] = {}
        self._parameters: dict[int, tuple[str, str]] = {}
        self._buffers: dict[int, tuple[str, str]] = {}
        self._boundary_by_tensor: dict[str, tuple[str, str]] = {}
        self._pending_recovery: list[tuple[dict[str, Any], str, int]] = []
        self._handles: list[Any] = []
        for module_path, module in model.named_modules():
            path = module_path or "<root>"
            module_id = module_ids[id(module)]
            for name, value in module.named_parameters(recurse=False):
                self._parameters[id(value)] = (module_id, f"{path}.{name}")
            for name, value in module.named_buffers(recurse=False):
                self._buffers[id(value)] = (module_id, f"{path}.{name}")

    def _storage_id(self, value: torch.Tensor) -> str | None:
        try:
            storage = value.untyped_storage()
            key = (str(value.device), int(storage.data_ptr()), int(storage.nbytes()))
            if key not in self._storage_id_by_runtime_key:
                self._storage_id_by_runtime_key[key] = f"storage-{len(self._storage_id_by_runtime_key):06d}"
            return self._storage_id_by_runtime_key[key]
        except RuntimeError:
            return None

    def tensor_id(self, value: torch.Tensor) -> str:
        object_id = id(value)
        existing = self._tensor_id_by_object.get(object_id)
        if existing:
            return existing
        tensor_id = f"tensor-{len(self.tensors):06d}"
        self._tensor_id_by_object[object_id] = tensor_id
        self._tensor_refs[tensor_id] = value
        storage_id = self._storage_id(value)
        record = {
            "tensor_id": tensor_id,
            **tensor_metadata(value),
            "storage_id": storage_id,
            "base_tensor_id": None,
            "alias_kind": "value",
            "is_view": False,
            "is_copy": False,
            "is_inplace": False,
            "mutation_history": [],
        }
        self.tensors.append(record)
        self._tensor_by_id[tensor_id] = record
        base = getattr(value, "_base", None)
        if torch.is_tensor(base) and id(base) != object_id:
            record["base_tensor_id"] = self.tensor_id(base)
            record["alias_kind"] = "view"
            record["is_view"] = True
        return tensor_id

    @staticmethod
    def _mutation_version(value: torch.Tensor) -> int | None:
        try:
            return int(value._version)
        except RuntimeError:
            return None

    def _port(
        self,
        node_id: str,
        direction: str,
        index: int,
        name: str,
        value: torch.Tensor,
        binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tensor_id = self.tensor_id(value)
        tensor = self._tensor_by_id[tensor_id]
        binding = binding or {}
        required = bool(binding.get("required", direction == "output"))
        return {
            "port_id": f"{node_id}:{'in' if direction == 'input' else 'out'}:{index}",
            "direction": direction,
            "index": index,
            "name": name,
            "tensor_id": tensor_id,
            "shape": tensor["shape"],
            "dtype": tensor["dtype"],
            "device": tensor["device"],
            "container_path": name,
            "alias_kind": "view" if tensor["base_tensor_id"] else "value",
            "is_view": bool(tensor["base_tensor_id"]),
            "is_copy": False,
            "is_inplace": False,
            "mutation_version": self._mutation_version(value),
            "mutation_version_before": self._mutation_version(value),
            "mutation_version_after": self._mutation_version(value),
            "required": required,
            "optional": bool(binding.get("optional", not required)),
            "argument_kind": binding.get(
                "argument_kind", "return" if direction == "output" else "runtime"
            ),
            "supplied_by": binding.get(
                "supplied_by", "runtime_output" if direction == "output" else "runtime"
            ),
            "position": binding.get("position", index if direction == "input" else None),
            "keyword_name": binding.get("keyword_name"),
        }

    def _annotate_operator_relationships(
        self,
        node_id: str,
        operator_name: str,
        inputs: list[tuple[str, torch.Tensor, dict[str, Any]]],
        input_ports: list[dict[str, Any]],
        outputs: list[tuple[str, torch.Tensor, dict[str, Any]]],
        output_ports: list[dict[str, Any]],
    ) -> None:
        input_by_object = {id(value): port for (_, value, _), port in zip(inputs, input_ports, strict=False)}
        input_storage = {
            self._tensor_by_id[port["tensor_id"]].get("storage_id"): port
            for port in input_ports
            if self._tensor_by_id[port["tensor_id"]].get("storage_id")
        }
        schema = operator_name.split(".")
        copy_operation = any(token in {"clone", "copy", "_to_copy", "contiguous"} for token in schema)
        for (_, value, binding), port in zip(inputs, input_ports, strict=False):
            after = self._mutation_version(value)
            before = port["mutation_version_before"]
            schema_write = bool(binding.get("schema_write"))
            mutated = schema_write or (before is not None and after is not None and after != before)
            port.update({
                "mutation_version_after": after,
                "mutation_version": after,
                "is_inplace": mutated,
                "alias_kind": "in_place_input" if mutated else port["alias_kind"],
            })
            tensor = self._tensor_by_id[port["tensor_id"]]
            tensor["mutation_version"] = after
            if mutated:
                tensor["alias_kind"] = "in_place"
                tensor["is_inplace"] = True
                tensor["mutation_history"].append({
                    "node_id": node_id,
                    "version_before": before,
                    "version_after": after,
                })
        for (_, value, _), port in zip(outputs, output_ports, strict=False):
            same_object = input_by_object.get(id(value))
            storage_id = self._tensor_by_id[port["tensor_id"]].get("storage_id")
            same_storage = input_storage.get(storage_id)
            base = getattr(value, "_base", None)
            if same_object:
                alias_kind = "in_place"
            elif torch.is_tensor(base) and id(base) in input_by_object:
                alias_kind = "view"
            elif same_storage:
                alias_kind = "alias"
            elif copy_operation:
                alias_kind = "copy"
            else:
                alias_kind = "value"
            after = self._mutation_version(value)
            port.update({
                "alias_kind": alias_kind,
                "is_view": alias_kind in {"view", "alias"},
                "is_copy": alias_kind == "copy",
                "is_inplace": alias_kind == "in_place",
                "mutation_version": after,
                "mutation_version_after": after,
            })
            tensor = self._tensor_by_id[port["tensor_id"]]
            tensor.update({
                "alias_kind": alias_kind,
                "is_view": alias_kind in {"view", "alias"},
                "is_copy": alias_kind == "copy",
                "is_inplace": alias_kind == "in_place",
                "mutation_version": after,
            })

    def _constant_node(self, tensor_id: str, kind: str, label: str, module_id: str | None) -> tuple[str, str]:
        node_id = f"{kind}-{len(self.nodes):06d}"
        value = self._tensor_refs[tensor_id]
        output = self._port(node_id, "output", 0, label, value, {
            "argument_kind": "boundary",
            "required": True,
            "optional": False,
            "supplied_by": "runtime_output",
        })
        self.nodes.append({
            "id": node_id,
            "kind": kind,
            "name": label,
            "display_name": label,
            "module_id": module_id,
            "module_path": self._module_by_id.get(module_id, {}).get("qualified_name") if module_id else None,
            "call_id": None,
            "layer_group_id": self._module_by_id.get(module_id, {}).get("layer_group_id") if module_id else None,
            "source_ref": {"source_uid": None, "file": None, "symbol": None, "start_line": 0, "end_line": 0, "executed_line": 0},
            "input_ports": [],
            "output_ports": [output],
            "call_arguments": [],
            "attributes": {},
        })
        producer = (node_id, output["port_id"])
        self._producer_by_tensor[tensor_id] = producer
        storage_id = self._tensor_by_id[tensor_id]["storage_id"]
        if storage_id:
            self._producer_by_storage[storage_id] = (node_id, output["port_id"], tensor_id)
        return producer

    def _producer(
        self,
        value: torch.Tensor,
        consumer_index: int,
        *,
        literal: bool = False,
        module_id: str | None = None,
    ) -> tuple[str, str, str]:
        tensor_id = self.tensor_id(value)
        exact = self._producer_by_tensor.get(tensor_id)
        if exact:
            return exact[0], exact[1], "exact"
        metadata = self._tensor_by_id[tensor_id]
        storage_id = metadata["storage_id"]
        if storage_id and storage_id in self._producer_by_storage:
            node_id, port_id, _ = self._producer_by_storage[storage_id]
            return node_id, port_id, "lineage"
        object_id = id(value)
        if object_id in self._parameters:
            module_id, label = self._parameters[object_id]
            node_id, port_id = self._constant_node(tensor_id, "parameter", label, module_id)
            return node_id, port_id, "exact"
        if object_id in self._buffers:
            module_id, label = self._buffers[object_id]
            node_id, port_id = self._constant_node(tensor_id, "buffer", label, module_id)
            return node_id, port_id, "exact"
        if literal:
            node_id, port_id = self._constant_node(tensor_id, "literal", f"literal {consumer_index}", module_id)
            return node_id, port_id, "exact"
        if tensor_id in self._boundary_by_tensor:
            node_id, port_id = self._boundary_by_tensor[tensor_id]
            return node_id, port_id, "exact"
        node_id, port_id = self._constant_node(tensor_id, "unresolved_input", f"unresolved input {consumer_index}", None)
        return node_id, port_id, "unresolved"

    def seed_inputs(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        values = _named_call_tensors(self.model.forward, args, kwargs)
        if not values:
            return
        node_id = "graph-input"
        ports = [
            self._port(node_id, "output", index, name, value, binding)
            for index, (name, value, binding) in enumerate(values)
        ]
        self.nodes.append({
            "id": node_id,
            "kind": "graph_input",
            "name": "Model inputs",
            "display_name": "Model inputs",
            "module_id": self.module_ids[id(self.model)],
            "module_path": "<root>",
            "call_id": None,
            "layer_group_id": None,
            "source_ref": source_ref(type(self.model).forward),
            "input_ports": [],
            "output_ports": ports,
            "call_arguments": _non_tensor_arguments(
                _bound_values(self.model.forward, args, kwargs),
                _binding_metadata(self.model.forward, args, kwargs),
            ),
            "attributes": {},
        })
        for port in ports:
            producer = (node_id, port["port_id"])
            self._producer_by_tensor[port["tensor_id"]] = producer
            self._boundary_by_tensor[port["tensor_id"]] = producer
            storage_id = self._tensor_by_id[port["tensor_id"]]["storage_id"]
            if storage_id:
                self._producer_by_storage[storage_id] = (node_id, port["port_id"], port["tensor_id"])

    def finish_outputs(self, output: Any) -> list[dict[str, Any]]:
        values = _named_outputs(output)
        node_id = "graph-output"
        ports = [self._port(node_id, "input", index, name, value, {
            "argument_kind": "return",
            "required": True,
            "optional": False,
            "supplied_by": "runtime_output",
        }) for index, (name, value) in enumerate(values)]
        self.nodes.append({
            "id": node_id,
            "kind": "graph_output",
            "name": "Model outputs",
            "display_name": "Model outputs",
            "module_id": self.module_ids[id(self.model)],
            "module_path": "<root>",
            "call_id": None,
            "layer_group_id": None,
            "source_ref": source_ref(type(self.model).forward),
            "input_ports": ports,
            "output_ports": [],
            "call_arguments": [],
            "attributes": {},
        })
        for index, ((_, value), port) in enumerate(zip(values, ports, strict=False)):
            source_node, source_port, confidence = self._producer(value, index)
            self.edges.append({
                "edge_id": f"edge-{len(self.edges):07d}",
                "source": source_node,
                "source_port": source_port,
                "target": node_id,
                "target_port": port["port_id"],
                "tensor_id": port["tensor_id"],
                "shape": port["shape"],
                "confidence": confidence,
                "evidence": ["producer_consumer"] if confidence == "exact" else [confidence],
            })
        return [{"role": "output", **port} for port in ports]

    def _source_frame(self) -> dict[str, Any]:
        frame = inspect.currentframe()
        if frame is not None:
            frame = frame.f_back
        fallback: FrameType | None = None
        while frame is not None:
            path = normalized_source_path(frame.f_code.co_filename)
            if path and path != "src/model_builder/tracing.py":
                if path.startswith(("transformers/", "diffusers/", "torch/nn/", "src/")):
                    if not path.startswith(("torch/_ops.py", "torch/utils/", "torch/_library/")):
                        return source_ref_from_frame(frame)
                if fallback is None and not path.startswith("torch/"):
                    fallback = frame
            frame = frame.f_back
        return source_ref_from_frame(fallback) if fallback is not None else {
            "source_uid": None, "file": None, "symbol": None,
            "start_line": 0, "end_line": 0, "executed_line": 0,
        }

    def _schema_values(
        self, func: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[list[tuple[str, torch.Tensor, dict[str, Any]]], list[dict[str, Any]]]:
        schema_arguments = list(getattr(getattr(func, "_schema", None), "arguments", []))
        values: dict[str, Any] = {}
        bindings: dict[str, dict[str, Any]] = {}
        for index, value in enumerate(args):
            schema_argument = schema_arguments[index] if index < len(schema_arguments) else None
            name = schema_argument.name if schema_argument else f"arg[{index}]"
            values[name] = value
            required = not schema_argument.has_default_value() if schema_argument else True
            bindings[name] = {
                "argument_kind": "keyword_only" if getattr(schema_argument, "kwarg_only", False) else "positional",
                "required": required,
                "optional": not required,
                "supplied_by": "positional",
                "position": index,
                "keyword_name": None,
                "schema_write": bool(getattr(getattr(schema_argument, "alias_info", None), "is_write", False)),
            }
        for name, value in kwargs.items():
            values[name] = value
            schema_argument = next((item for item in schema_arguments if item.name == name), None)
            required = not schema_argument.has_default_value() if schema_argument else True
            bindings[name] = {
                "argument_kind": "keyword_only" if getattr(schema_argument, "kwarg_only", False) else "keyword",
                "required": required,
                "optional": not required,
                "supplied_by": "keyword",
                "position": None,
                "keyword_name": name,
                "schema_write": bool(getattr(getattr(schema_argument, "alias_info", None), "is_write", False)),
            }
        tensors: list[tuple[str, torch.Tensor, dict[str, Any]]] = []
        for name, value in values.items():
            tensors.extend(
                (path, tensor, bindings.get(name, {}))
                for path, tensor in _flatten_named(value, name)
            )
        return tensors, _non_tensor_arguments(values, bindings)

    def _schema_outputs(
        self, func: Any, output: Any
    ) -> list[tuple[str, torch.Tensor, dict[str, Any]]]:
        values = _named_outputs(output)
        returns = list(getattr(getattr(func, "_schema", None), "returns", []))
        if len(values) == len(returns) and returns:
            renamed = []
            for index, ((fallback, value), schema_return) in enumerate(zip(values, returns, strict=False)):
                name = schema_return.name or ("output" if len(values) == 1 else f"output[{index}]")
                renamed.append((name or fallback, value, {
                    "argument_kind": "return",
                    "required": True,
                    "optional": False,
                    "supplied_by": "runtime_output",
                }))
            return renamed
        return [(name, value, {
            "argument_kind": "return",
            "required": True,
            "optional": False,
            "supplied_by": "runtime_output",
        }) for name, value in values]

    def __torch_dispatch__(
        self,
        func: Any,
        types: tuple[type, ...],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        kwargs = kwargs or {}
        input_values, call_arguments = self._schema_values(func, args, kwargs)
        node_id = f"op-{len([node for node in self.nodes if node['kind'] == 'aten_op']):06d}"
        input_ports = [
            self._port(node_id, "input", index, name, value, binding)
            for index, (name, value, binding) in enumerate(input_values)
        ]
        output = func(*args, **kwargs)
        output_values = self._schema_outputs(func, output)
        output_ports = [
            self._port(node_id, "output", index, name, value, binding)
            for index, (name, value, binding) in enumerate(output_values)
        ]
        call_id = self.call_stack[-1] if self.call_stack else None
        call = self._call_by_id.get(call_id, {})
        module_id = call.get("module_id")
        module_path = call.get("qualified_name")
        name = str(func)
        self._annotate_operator_relationships(
            node_id, name, input_values, input_ports, output_values, output_ports
        )
        self.nodes.append({
            "id": node_id,
            "kind": "aten_op",
            "name": name,
            "display_name": name.removeprefix("aten.").split(".")[0],
            "module_id": module_id,
            "module_path": module_path,
            "call_id": call_id,
            "layer_group_id": self.layer_for_path.get(module_path),
            "source_ref": self._source_frame(),
            "input_ports": input_ports,
            "output_ports": output_ports,
            "call_arguments": call_arguments,
            "attributes": {"schema": str(getattr(func, "_schema", ""))},
        })
        operation_position = len(self.nodes) - 1
        for index, ((_, value, _), port) in enumerate(zip(input_values, input_ports, strict=False)):
            source_node, source_port, confidence = self._producer(
                value,
                index,
                literal=name.startswith("aten.lift_fresh"),
                module_id=module_id,
            )
            edge = {
                "edge_id": f"edge-{len(self.edges):07d}",
                "source": source_node,
                "source_port": source_port,
                "target": node_id,
                "target_port": port["port_id"],
                "tensor_id": port["tensor_id"],
                "shape": port["shape"],
                "confidence": confidence,
                "evidence": (
                    ["literal_boundary", "operator_schema"]
                    if name.startswith("aten.lift_fresh") and confidence == "exact"
                    else (["producer_consumer"] if confidence == "exact" else [confidence])
                ),
            }
            self.edges.append(edge)
            if confidence == "unresolved":
                self._pending_recovery.append((edge, port["tensor_id"], operation_position))
        for port in output_ports:
            tensor_id = port["tensor_id"]
            self._producer_by_tensor[tensor_id] = (node_id, port["port_id"])
            storage_id = self._tensor_by_id[tensor_id]["storage_id"]
            if storage_id:
                self._producer_by_storage[storage_id] = (node_id, port["port_id"], tensor_id)
        return output

    def _pre_hook(self, module: nn.Module, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        module_id = self.module_ids[id(module)]
        path = self.module_paths[id(module)]
        call_id = f"call-{len(self.calls):06d}"
        values = _named_call_tensors(module.forward, args, kwargs)
        call = {
            "call_id": call_id,
            "call_index": len(self.calls),
            "module_id": module_id,
            "qualified_name": path,
            "parent_call_id": self.call_stack[-1] if self.call_stack else None,
            "source_ref": source_ref(type(module).forward),
            "input_ports": [
                self._port(call_id, "input", index, name, value, binding)
                for index, (name, value, binding) in enumerate(values)
            ],
            "output_ports": [],
            "call_arguments": _non_tensor_arguments(
                _bound_values(module.forward, args, kwargs),
                _binding_metadata(module.forward, args, kwargs),
            ),
            "operation_ids": [],
            "trace_confidence": "exact",
        }
        self.calls.append(call)
        self._call_by_id[call_id] = call
        self._module_by_id[module_id]["call_ids"].append(call_id)
        self.call_stack.append(call_id)

    def _post_hook(
        self,
        module: nn.Module,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        output: Any,
    ) -> None:
        module_id = self.module_ids[id(module)]
        call_id = next(
            (value for value in reversed(self.call_stack) if self._call_by_id[value]["module_id"] == module_id),
            None,
        )
        if call_id is None:
            return
        call = self._call_by_id[call_id]
        values = _named_outputs(output)
        call["output_ports"] = [self._port(call_id, "output", index, name, value, {
            "argument_kind": "return",
            "required": True,
            "optional": False,
            "supplied_by": "runtime_output",
        }) for index, (name, value) in enumerate(values)]
        call["operation_ids"] = [
            node["id"] for node in self.nodes
            if node["kind"] == "aten_op" and node["call_id"] == call_id
        ]
        self.call_stack.remove(call_id)

    def install_hooks(self) -> None:
        for module in self.model.modules():
            self._handles.append(module.register_forward_pre_hook(self._pre_hook, with_kwargs=True))
            self._handles.append(module.register_forward_hook(
                self._post_hook, with_kwargs=True, always_call=True
            ))

    def remove_hooks(self) -> None:
        for handle in self._handles:
            handle.remove()
        self._handles.clear()

    def recover_unresolved(self) -> dict[str, int]:
        counts = {"exact": 0, "lineage": 0, "inferred": 0, "ambiguous": 0, "unresolved": 0}
        for edge in self.edges:
            counts[edge["confidence"]] += 1
        for edge, input_tensor_id, node_position in self._pending_recovery:
            target = self._tensor_refs[input_tensor_id]
            if target.numel() > 1_000_000:
                continue
            candidates: list[tuple[str, str]] = []
            target_meta = self._tensor_by_id[input_tensor_id]
            prior_nodes = self.nodes[:node_position]
            for node in reversed(prior_nodes[-256:]):
                for port in node["output_ports"]:
                    if port["shape"] != target_meta["shape"] or port["dtype"] != target_meta["dtype"]:
                        continue
                    candidate = self._tensor_refs[port["tensor_id"]]
                    try:
                        if torch.equal(candidate, target):
                            candidates.append((node["id"], port["port_id"]))
                    except RuntimeError:
                        continue
            counts["unresolved"] -= 1
            if len(candidates) == 1:
                edge.update({
                    "source": candidates[0][0],
                    "source_port": candidates[0][1],
                    "confidence": "inferred",
                    "evidence": ["bounded_value_search", "shape", "dtype", "call_order"],
                })
                counts["inferred"] += 1
            elif candidates:
                edge.update({"confidence": "ambiguous", "evidence": ["bounded_value_search", "multiple_matches"]})
                counts["ambiguous"] += 1
            else:
                counts["unresolved"] += 1
        return counts


def _line_traces(
    recorder: LineRecorder,
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for file, lines in sorted(recorder.lines.items()):
        file_nodes = [node for node in nodes if node["source_ref"].get("file") == file]
        for line in sorted(lines):
            matching = [
                node for node in file_nodes
                if node["source_ref"]["start_line"] <= line <= node["source_ref"]["end_line"]
                and (
                    node["source_ref"]["executed_line"] == line
                    or node["source_ref"]["start_line"] == node["source_ref"]["end_line"]
                )
            ]
            result.append({
                "line_trace_id": "line.sha256." + sha256_json([file, line, [node["id"] for node in matching]]),
                "source_uid": matching[0]["source_ref"]["source_uid"] if matching else (
                    "source.sha256." + hashlib.sha256(file.encode()).hexdigest()
                ),
                "file": file,
                "line": line,
                "code_hash": "sha256.pending-source-asset",
                "executed": True,
                "op_ids": [node["id"] for node in matching],
                "input_shapes": [port for node in matching for port in node["input_ports"]],
                "output_shapes": [port for node in matching for port in node["output_ports"]],
                "variables": [],
                "control_context": [],
                "confidence": "exact" if matching else "partial",
            })
    return result


def _package_roots() -> tuple[Path, ...]:
    roots = []
    for package in ("torch", "transformers", "diffusers"):
        try:
            imported = __import__(package)
            roots.append(Path(imported.__file__).resolve().parent)
        except (ImportError, TypeError):
            pass
    return tuple(roots)


def trace_model(
    model: nn.Module,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    version_id: str,
    constructors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    constructors = constructors or []
    modules, module_ids, module_paths = _module_records(model, constructors)
    layer_groups, layer_for_path = _assign_layer_groups(model, modules)
    graph = RuntimeGraphRecorder(
        version_id, model, modules, module_ids, module_paths, layer_for_path
    )
    graph.seed_inputs(args, kwargs)
    graph.install_hooks()
    try:
        with LineRecorder(_package_roots()) as line_recorder, graph, torch.inference_mode():
            output = model(*args, **kwargs)
    except RuntimeError as exc:
        cause = exc.__cause__
        if cause is not None:
            raise RuntimeError(f"{exc}: {type(cause).__name__}: {cause}") from cause
        raise
    finally:
        graph.remove_hooks()
    top_level_outputs = graph.finish_outputs(output)
    confidence_counts = graph.recover_unresolved()

    for module in modules:
        prefix = "" if module["qualified_name"] == "<root>" else f"{module['qualified_name']}."
        owned = [
            node for node in graph.nodes
            if node["kind"] == "aten_op" and (
                node["module_path"] == module["qualified_name"]
                or (prefix and str(node["module_path"] or "").startswith(prefix))
            )
        ]
        module["observed_topology_signature"] = "topology.sha256." + sha256_json([
            (
                node["name"],
                [port["shape"] for port in node["input_ports"]],
                [port["shape"] for port in node["output_ports"]],
            )
            for node in owned
        ])
    module_by_id = {module["module_id"]: module for module in modules}
    calls_by_id = {call["call_id"]: call for call in graph.calls}
    for group in layer_groups:
        module = module_by_id[group["module_id"]]
        calls = [calls_by_id[call_id] for call_id in module["call_ids"] if call_id in calls_by_id]
        group["runtime_signature"] = "layer.sha256." + sha256_json({
            "structure": module["structural_signature"],
            "topology": module["observed_topology_signature"],
            "io": [
                (
                    [port["shape"] for port in call["input_ports"]],
                    [port["shape"] for port in call["output_ports"]],
                )
                for call in calls
            ],
        })

    operations = [{
        "op_id": node["id"],
        "model_version_id": version_id,
        "block_uid": None,
        "parent_module_id": node["module_id"],
        "call_index": index,
        "kind": node["kind"],
        "qualified_name": node["module_path"] or node["name"],
        "display_name": node["display_name"],
        "target": node["name"],
        "source_ref": node["source_ref"],
        "stack": [],
        "inputs": [{"role": "input", **port} for port in node["input_ports"]],
        "outputs": [{"role": "output", **port} for port in node["output_ports"]],
        "attributes": node["attributes"],
        "call_arguments": node["call_arguments"],
        "config_conditions": [],
        "children": [],
        "trace_confidence": "exact",
    } for index, node in enumerate(graph.nodes) if node["kind"] == "aten_op"]
    canonical_graph = {
        "schema_version": SCHEMA_VERSION,
        "tracer": "torch-dispatch-lineage",
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "nodes": graph.nodes,
        "edges": graph.edges,
        "tensors": graph.tensors,
        "modules": modules,
        "module_calls": graph.calls,
        "layer_groups": layer_groups,
        "trace_modes": {
            "exact_lineage": "completed",
            "deep_recovery": "completed" if graph._pending_recovery else "not_required",
            "confidence_counts": confidence_counts,
        },
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_mode": "full_model_forward",
        "status": "passed",
        "device": "cpu",
        "trace_event_count": len(operations),
        "top_level_outputs": top_level_outputs,
        "operations": operations,
        "module_calls": graph.calls,
        "modules": modules,
        "layer_groups": layer_groups,
        "line_traces": _line_traces(line_recorder, graph.nodes),
        "trace_modes": canonical_graph["trace_modes"],
        "graph": canonical_graph,
        "torchview": canonical_graph,
    }
