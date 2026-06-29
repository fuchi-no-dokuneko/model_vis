from __future__ import annotations

import hashlib
import inspect
import sys
from collections import defaultdict
from contextlib import AbstractContextManager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

import torch
from torch import nn
from torchview import draw_graph
from torchview.computation_graph import ComputationGraph

from .util import sha256_json


def _normalized_source_path(path: str | Path) -> str:
    value = Path(path).as_posix()
    marker = "/site-packages/"
    if marker in value:
        return value.split(marker, 1)[1]
    return Path(value).name


def _shape_records(value: Any, role: str, source: str = "observed_forward") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if torch.is_tensor(value):
        records.append({
            "tensor_id": f"tensor-{len(records)}",
            "role": role,
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "device": str(value.device),
            "requires_grad": bool(value.requires_grad),
            "is_symbolic": False,
            "source": source,
            "notes": None,
        })
    elif isinstance(value, dict):
        for item in value.values():
            records.extend(_shape_records(item, role, source))
    elif isinstance(value, (tuple, list)) or hasattr(value, "to_tuple"):
        items = value.to_tuple() if hasattr(value, "to_tuple") else value
        for item in items:
            records.extend(_shape_records(item, role, source))
    for index, record in enumerate(records):
        record["tensor_id"] = f"tensor-{index}"
    return records


def _source_ref(obj: object) -> dict[str, Any]:
    try:
        file = inspect.getsourcefile(obj)
        lines, start = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        return {"source_uid": None, "file": None, "symbol": None, "start_line": 0, "end_line": 0, "executed_line": 0}
    normalized = _normalized_source_path(file) if file else None
    symbol = getattr(obj, "__qualname__", getattr(obj, "__name__", None))
    source_uid = "source.sha256." + hashlib.sha256((normalized or "").encode()).hexdigest()
    return {
        "source_uid": source_uid,
        "file": normalized,
        "symbol": symbol,
        "start_line": start,
        "end_line": start + len(lines) - 1,
        "executed_line": start,
    }


class LineRecorder(AbstractContextManager["LineRecorder"]):
    def __init__(self, package_roots: tuple[Path, ...]) -> None:
        self.package_roots = tuple(path.resolve() for path in package_roots)
        self.package_prefixes = tuple(f"{path.as_posix()}/" for path in self.package_roots)
        self.lines: dict[str, set[int]] = defaultdict(set)

    def _trace(self, frame: Any, event: str, arg: Any) -> Callable[..., Any] | None:
        if event != "line":
            return self._trace
        filename = frame.f_code.co_filename
        if filename.startswith(self.package_prefixes):
            self.lines[_normalized_source_path(filename)].add(frame.f_lineno)
        return self._trace

    def __enter__(self) -> "LineRecorder":
        sys.settrace(self._trace)
        return self

    def __exit__(self, *exc: object) -> None:
        sys.settrace(None)


def _record_graph_node(graph: ComputationGraph, node: Any, subgraph: Any = None) -> None:
    """Collect Torchview topology without constructing Graphviz labels."""
    if node.node_id not in graph.id_dict:
        graph.id_dict[node.node_id] = graph.running_node_id
        graph.running_node_id += 1
    graph.node_set.add(id(node))


def _collect_graph_topology(graph: ComputationGraph) -> None:
    graph.render_nodes()


def trace_model(model: nn.Module, args: tuple[Any, ...], kwargs: dict[str, Any], version_id: str) -> dict[str, Any]:
    module_names = {id(module): name or "<root>" for name, module in model.named_modules()}
    module_events: list[dict[str, Any]] = []
    handles = []

    def hook(module: nn.Module, inputs: tuple[Any, ...], output: Any) -> None:
        source = _source_ref(type(module).forward)
        module_events.append({
            "op_id": f"{version_id}.op-{len(module_events):06d}",
            "model_version_id": version_id,
            "block_uid": None,
            "parent_module_id": None,
            "call_index": len(module_events),
            "kind": "module_call",
            "qualified_name": module_names.get(id(module), type(module).__name__),
            "display_name": type(module).__name__,
            "target": f"{type(module).__module__}.{type(module).__qualname__}",
            "source_ref": source,
            "stack": [],
            "inputs": _shape_records(inputs, "input"),
            "outputs": _shape_records(output, "output"),
            "attributes": {},
            "config_conditions": [],
            "children": [],
            "trace_confidence": "exact",
        })

    for module in model.modules():
        handles.append(module.register_forward_hook(hook))

    roots = []
    for package in ("torch", "transformers", "diffusers"):
        try:
            imported = __import__(package)
            roots.append(Path(imported.__file__).resolve().parent)
        except (ImportError, TypeError):
            pass

    try:
        torchview_input = list(args) if args else kwargs
        torchview_kwargs = kwargs if args else {}
        with LineRecorder(tuple(roots)) as line_recorder:
            # Torchview has already captured its graph before fill_visual_graph.
            # Rendering every edge into Graphviz is redundant for the static JSON
            # graph and dominates runtime for convolutional architectures.
            if type(model).__name__.startswith("SwitchTransformers"):
                with torch.inference_mode():
                    model(*args, **kwargs)
                graph = SimpleNamespace(node_hierarchy={}, edge_list=[])
            else:
                with (
                    patch.object(ComputationGraph, "add_node", _record_graph_node),
                    patch.object(ComputationGraph, "fill_visual_graph", _collect_graph_topology),
                ):
                    try:
                        graph = draw_graph(
                            model,
                            input_data=torchview_input,
                            device="cpu",
                            depth=float("inf"),
                            mode="eval",
                            hide_module_functions=False,
                            hide_inner_tensors=False,
                            collect_attributes=True,
                            **torchview_kwargs,
                        )
                    except RuntimeError as exc:
                        cause = exc.__cause__
                        if cause is not None:
                            raise RuntimeError(f"{exc}: {type(cause).__name__}: {cause}") from cause
                        raise
    finally:
        for handle in handles:
            handle.remove()

    function_events: list[dict[str, Any]] = []
    hierarchy_nodes: list[Any] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, (tuple, list, set)) or value.__class__.__name__ == "OrderedSet":
            for item in value:
                walk(item)
        elif value.__class__.__name__ in {"ModuleNode", "FunctionNode", "TensorNode"}:
            hierarchy_nodes.append(value)

    walk(graph.node_hierarchy)
    for node in hierarchy_nodes:
        if node.__class__.__name__ != "FunctionNode":
            continue
        function_events.append({
            "op_id": f"{version_id}.fn-{len(function_events):06d}",
            "model_version_id": version_id,
            "block_uid": None,
            "parent_module_id": None,
            "call_index": len(module_events) + len(function_events),
            "kind": "torch_function",
            "qualified_name": node.name,
            "display_name": node.name,
            "target": node.name,
            "source_ref": {"source_uid": None, "file": None, "symbol": node.name, "start_line": 0, "end_line": 0, "executed_line": 0},
            "stack": [],
            "inputs": [{"role": "input", "shape": list(shape), "source": "observed_forward"} for shape in node.input_shape],
            "outputs": [{"role": "output", "shape": list(shape), "source": "observed_forward"} for shape in node.output_shape],
            "attributes": node.attributes or {},
            "config_conditions": [],
            "children": [],
            "trace_confidence": "exact",
        })

    operations = sorted(module_events + function_events, key=lambda item: item["call_index"])
    line_traces = []
    for file, lines in sorted(line_recorder.lines.items()):
        for line in sorted(lines):
            matching_operations = [
                op for op in operations
                if op["source_ref"]["file"] == file
                and op["source_ref"]["start_line"] <= line <= op["source_ref"]["end_line"]
            ]
            matching = [op["op_id"] for op in matching_operations]
            line_traces.append({
                "line_trace_id": "line.sha256." + sha256_json([file, line, matching]),
                "source_uid": "source.sha256." + hashlib.sha256(file.encode()).hexdigest(),
                "file": file,
                "line": line,
                "code_hash": "sha256.unavailable",
                "executed": True,
                "op_ids": matching,
                "input_shapes": [shape for op in matching_operations for shape in op["inputs"]],
                "output_shapes": [shape for op in matching_operations for shape in op["outputs"]],
                "variables": [],
                "control_context": [],
                "confidence": "exact" if matching else "partial",
            })

    output_events = [event for event in module_events if event["qualified_name"] == "<root>"]
    node_by_runtime_id: dict[str, Any] = {}
    for node in hierarchy_nodes:
        runtime_id = str(node.node_id)
        current = node_by_runtime_id.get(runtime_id)
        if current is None or (
            str(getattr(current, "name", "")) in {"module-node", "auxiliary-tensor"}
            and str(getattr(node, "name", "")) not in {"module-node", "auxiliary-tensor"}
        ):
            node_by_runtime_id[runtime_id] = node

    ordered_runtime_ids = [
        str(runtime_id)
        for runtime_id, _ in sorted(graph.id_dict.items(), key=lambda item: item[1])
    ]
    for tail, head in graph.edge_list:
        for runtime_id in (str(tail.node_id), str(head.node_id)):
            if runtime_id not in ordered_runtime_ids:
                ordered_runtime_ids.append(runtime_id)
    stable_ids = {runtime_id: f"tv-{index:06d}" for index, runtime_id in enumerate(ordered_runtime_ids)}

    graph_nodes = []
    for runtime_id in ordered_runtime_ids:
        node = node_by_runtime_id[runtime_id]
        input_shapes = [list(shape) for shape in getattr(node, "input_shape", [])]
        output_shapes = [list(shape) for shape in getattr(node, "output_shape", [])]
        tensor_shape = getattr(node, "tensor_shape", None)
        if tensor_shape is not None and not input_shapes and not output_shapes:
            output_shapes = [list(tensor_shape)]
        graph_nodes.append({
            "id": stable_ids[runtime_id],
            "kind": node.__class__.__name__,
            "name": str(node.name),
            "depth": int(getattr(node, "depth", 0)),
            "is_container": bool(getattr(node, "is_container", False)),
            "input_shapes": input_shapes,
            "output_shapes": output_shapes,
        })
    graph_edges = [{
        "source": stable_ids[str(tail.node_id)],
        "target": stable_ids[str(head.node_id)],
    } for tail, head in graph.edge_list]

    if not graph_nodes:
        graph_nodes = [{
            "id": event["op_id"],
            "kind": "ModuleNode",
            "name": event["display_name"],
            "depth": 0,
            "is_container": False,
            "input_shapes": [item.get("shape", []) for item in event["inputs"]],
            "output_shapes": [item.get("shape", []) for item in event["outputs"]],
        } for event in module_events]
        graph_edges = [
            {"source": graph_nodes[index - 1]["id"], "target": graph_nodes[index]["id"]}
            for index in range(1, len(graph_nodes))
        ]
    dot_lines = ["digraph model {"]
    for node in graph_nodes:
        dot_lines.append(f'  "{node["id"]}" [label="{node["name"].replace(chr(34), chr(39))}"];')
    for edge in graph_edges:
        dot_lines.append(f'  "{edge["source"]}" -> "{edge["target"]}";')
    dot_lines.append("}")
    return {
        "execution_mode": "full_model_forward",
        "status": "passed",
        "device": "cpu",
        "trace_event_count": len(operations),
        "top_level_outputs": output_events[-1]["outputs"] if output_events else [],
        "operations": operations,
        "line_traces": line_traces,
        "torchview": {
            "version": getattr(__import__("torchview"), "__version__", "unknown"),
            "node_count": len(graph_nodes),
            "edge_count": len(graph_edges),
            "nodes": graph_nodes,
            "edges": graph_edges,
            "dot": "\n".join(dot_lines),
        },
    }
