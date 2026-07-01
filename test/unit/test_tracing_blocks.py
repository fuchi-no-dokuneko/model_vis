import torch
from torch import nn

from src.model_builder.blocks import build_blocks
from src.model_builder.introspection import ConstructorRecorder, sanitize_runtime_value
from src.model_builder.tracing import trace_model


class CountedLayers(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.ModuleList([nn.Linear(4, 4), nn.Linear(4, 4)])
        self.forward_count = 0

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        self.forward_count += 1
        for layer in self.layers:
            value = layer(value)
        return value


class BranchedResidual(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.query = nn.Linear(4, 4, bias=False)
        self.key = nn.Linear(4, 4, bias=False)
        self.value = nn.Linear(4, 4, bias=False)

    def forward(self, hidden_states: torch.Tensor, residual: torch.Tensor) -> torch.Tensor:
        query = self.query(hidden_states)
        key = self.key(hidden_states)
        value = self.value(hidden_states)
        return query + key + value + residual


class UnregisteredConstant(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.constant = torch.ones(1, 4)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return value + self.constant


class MultipleOutputs(nn.Module):
    def forward(self, value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        left, right = torch.chunk(value, 2, dim=-1)
        return left + 1, right * 2


class CopyAndMutation(nn.Module):
    def forward(self, value: torch.Tensor) -> torch.Tensor:
        copied = value.clone()
        copied.add_(1)
        return copied


class NestedLayer(nn.Module):
    def __init__(self, input_width: int, output_width: int) -> None:
        super().__init__()
        self.projection = nn.Linear(input_width, output_width)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.projection(value)


class DifferentNestedShapes(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.first = NestedLayer(4, 4)
        self.second = NestedLayer(4, 8)

    def forward(self, value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.first(value), self.second(value)


def test_torchview_executes_once_and_records_shapes() -> None:
    model = CountedLayers().eval()
    trace = trace_model(model, (torch.zeros(1, 4),), {}, "counted")

    assert model.forward_count == 1
    assert trace["status"] == "passed"
    assert trace["trace_event_count"] > 0
    assert trace["top_level_outputs"][0]["shape"] == [1, 4]
    assert trace["torchview"]["node_count"] > 0
    assert trace["torchview"]["nodes"]
    assert trace["torchview"]["edges"]


def test_identical_observed_layers_deduplicate() -> None:
    model = CountedLayers().eval()
    trace = trace_model(model, (torch.zeros(1, 4),), {}, "counted")
    blocks, shared = build_blocks(model, "counted", "counted-family", "sha256.counted", trace)
    layer_blocks = [block for block in blocks if block["qualified_name"] in {"layers.0", "layers.1"}]

    assert len(layer_blocks) == 2
    assert layer_blocks[0]["dedup_ref"] == layer_blocks[1]["dedup_ref"]
    assert layer_blocks[0]["dedup_ref"] in shared


def test_canonical_graph_preserves_parallel_fanout_residual_and_named_ports() -> None:
    model = BranchedResidual().eval()
    hidden = torch.zeros(1, 4)
    residual = torch.ones(1, 4)
    trace = trace_model(model, (hidden, residual), {}, "branched")
    graph = trace["graph"]

    input_node = next(node for node in graph["nodes"] if node["kind"] == "graph_input")
    hidden_port = next(port for port in input_node["output_ports"] if port["name"] == "hidden_states")
    fanout = [edge for edge in graph["edges"] if edge["tensor_id"] == hidden_port["tensor_id"]]

    assert len(fanout) == 3
    assert all(edge["confidence"] == "exact" for edge in graph["edges"])
    assert all(edge["source_port"] and edge["target_port"] for edge in graph["edges"])
    assert {port["name"] for port in input_node["output_ports"]} == {"hidden_states", "residual"}
    assert graph["trace_modes"]["deep_recovery"] == "not_required"


def test_constructor_recorder_captures_effective_runtime_values() -> None:
    with ConstructorRecorder() as recorder:
        model = BranchedResidual()
    records = recorder.records_for(model, {"in_features": 4, "out_features": 4, "bias": False})
    query = next(item for item in records if item["qualified_name"] == "query")
    arguments = {item["name"]: item["value"] for item in query["effective_arguments"]}

    assert query["capture_confidence"] == "actual_call"
    assert query["positional_arguments"] == [4, 4]
    assert query["keyword_arguments"] == {"bias": False}
    assert arguments["in_features"] == 4
    assert arguments["out_features"] == 4
    assert arguments["bias"] is False
    bias = next(item for item in query["effective_arguments"] if item["name"] == "bias")
    assert bias["supplied_by"] == "keyword"
    assert bias["origin"] == "config"
    assert bias["config_path"] == "bias"


def test_deep_recovery_runs_and_marks_unresolved_routes_without_inventing_edges() -> None:
    trace = trace_model(UnregisteredConstant().eval(), (torch.zeros(1, 4),), {}, "recovery")
    modes = trace["graph"]["trace_modes"]

    assert modes["deep_recovery"] == "completed"
    assert modes["confidence_counts"]["unresolved"] == 1
    assert any(edge["confidence"] == "unresolved" for edge in trace["graph"]["edges"])


def test_multiple_outputs_keep_distinct_named_ports_and_routes() -> None:
    trace = trace_model(MultipleOutputs().eval(), (torch.zeros(1, 4),), {}, "multiple")
    graph = trace["graph"]
    split = next(node for node in graph["nodes"] if len(node["output_ports"]) == 2)
    routed_tensors = {edge["tensor_id"] for edge in graph["edges"] if edge["source"] == split["id"]}

    assert [port["name"] for port in split["output_ports"]] == ["output[0]", "output[1]"]
    assert routed_tensors == {port["tensor_id"] for port in split["output_ports"]}
    assert {item["name"]: item["value"] for item in split["call_arguments"]} == {"chunks": 2, "dim": -1}


def test_ports_capture_binding_and_copy_mutation_lineage() -> None:
    trace = trace_model(CopyAndMutation().eval(), (torch.zeros(1, 4),), {}, "mutation")
    graph = trace["graph"]
    model_input = next(node for node in graph["nodes"] if node["kind"] == "graph_input")["output_ports"][0]
    clone = next(node for node in graph["nodes"] if node["name"] == "aten.clone.default")
    inplace = next(node for node in graph["nodes"] if node["name"] == "aten.add_.Tensor")

    assert model_input["required"] is True
    assert model_input["optional"] is False
    assert model_input["supplied_by"] == "positional"
    assert model_input["position"] == 0
    assert clone["output_ports"][0]["alias_kind"] == "copy"
    assert clone["output_ports"][0]["is_copy"] is True
    assert inplace["input_ports"][0]["is_inplace"] is True
    assert inplace["output_ports"][0]["alias_kind"] == "in_place"


def test_structural_signature_includes_descendant_parameter_shapes() -> None:
    graph = trace_model(DifferentNestedShapes().eval(), (torch.zeros(1, 4),), {}, "nested")["graph"]
    first = next(module for module in graph["modules"] if module["qualified_name"] == "first")
    second = next(module for module in graph["modules"] if module["qualified_name"] == "second")

    assert first["structural_signature"] != second["structural_signature"]


def test_runtime_sanitizer_redacts_secrets_and_local_paths() -> None:
    value = sanitize_runtime_value({
        "api_key": "do-not-serialize",
        "cache_path": "/home/example/private/cache.bin",
    })

    assert value["api_key"] == {"redacted": True}
    assert value["cache_path"] == {"type": "local_path", "name": "cache.bin"}
