import torch
from torch import nn

from src.model_builder.blocks import build_blocks
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
