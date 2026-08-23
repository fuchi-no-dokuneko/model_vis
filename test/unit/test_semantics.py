import json
from pathlib import Path

import torch
from torch import nn

from src.model_builder.semantics import (
    INTERFACE_TAGS_REF,
    SEMANTIC_GENERATOR_VERSION,
    SEMANTIC_SCHEMA_REF,
    assign_class_tags,
    generate_semantics,
    load_registry,
    publish_semantic_contracts,
    semantic_report_document,
    topological_node_ids,
)
from src.model_builder.tracing import trace_model


class TiedWeights(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.left = nn.Linear(4, 4, bias=False)
        self.right = nn.Linear(4, 4, bias=False)
        self.right.weight = self.left.weight

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.right(self.left(value))


def _version(model: nn.Module, version_id: str = "fixture") -> dict:
    total = sum(parameter.numel() for parameter in model.parameters())
    return {
        "version_id": version_id,
        "task_type": "text",
        "category": "Text models",
        "parameters": {"total": total, "trainable": total},
        "resource_preflight": {"estimated_parameter_count": total * 10},
    }


def test_exact_class_tag_has_priority_over_base_and_signature_rules() -> None:
    registry = {
        "tags": [
            {"id": "attention_or_mixer", "exact_classes": ["fixture.Class"], "base_classes": [], "verified_signatures": []},
            {"id": "feed_forward", "exact_classes": [], "base_classes": ["fixture.Base"], "verified_signatures": []},
            {"id": "other", "exact_classes": [], "base_classes": [], "verified_signatures": []},
        ]
    }
    module = {
        "class_name": "fixture.Class",
        "base_classes": ["fixture.Base"],
        "forward_interface": {"text": "forward(value)"},
    }

    result = assign_class_tags(module, registry)

    assert result["primary_tag"] == "attention_or_mixer"
    assert result["confidence"] == "verified_rule"
    assert result["provenance"][0] == "exact_class_rule"


def test_base_class_tag_has_priority_over_verified_signature_rule() -> None:
    registry = {
        "tags": [
            {"id": "feed_forward", "exact_classes": [], "base_classes": ["fixture.Base"], "verified_signatures": []},
            {"id": "attention_or_mixer", "exact_classes": [], "base_classes": [], "verified_signatures": ["forward(value)"]},
            {"id": "other", "exact_classes": [], "base_classes": [], "verified_signatures": []},
        ]
    }
    module = {
        "class_name": "fixture.Child",
        "base_classes": ["fixture.Base"],
        "forward_interface": {"text": "forward(value)"},
    }

    result = assign_class_tags(module, registry)

    assert result["primary_tag"] == "feed_forward"
    assert result["provenance"][0] == "exact_base_class_rule"


def test_semantic_generator_validates_fallbacks_and_deduplicates_tied_parameters() -> None:
    model = TiedWeights().eval()
    graph = trace_model(model, (torch.zeros(1, 4),), {}, "tied")["graph"]

    semantic = generate_semantics(
        _version(model, "tied"), graph, generated_at="2026-08-12T00:00:00Z", config={"is_encoder_decoder": False}
    )

    assert semantic["schema_version"] == "1.0.0"
    assert semantic["generator_version"] == SEMANTIC_GENERATOR_VERSION
    assert sum(item["value"] for item in semantic["metrics"]["parameter_distribution"]) == 16
    assert semantic["metrics"]["official_parameter_estimate"] == 160
    assert sum(item["value"] for item in semantic["metrics"]["operation_distribution"]) == semantic["metrics"]["trace_operation_total"]
    assert semantic["coverage"]["parameter_accounted_fraction"] == 1.0
    assert semantic["entities"]["module-00000"]["what"].startswith("Technical fallback:")
    assert set(semantic["entities"]) == {
        *(module["module_id"] for module in graph["modules"]),
        *(node["id"] for node in graph["nodes"]),
    }
    tensor_shapes = {tensor["tensor_id"]: tensor["shape"] for tensor in graph["tensors"]}
    assert all(
        step["shape"] == tensor_shapes[step["tensor_id"]]
        for journey in semantic["journeys"]
        for step in journey["steps"]
    )


def test_stage_order_follows_graph_dependencies() -> None:
    model = TiedWeights().eval()
    graph = trace_model(model, (torch.zeros(1, 4),), {}, "ordered")["graph"]
    semantic = generate_semantics(
        _version(model, "ordered"), graph, generated_at="2026-08-12T00:00:00Z", config={"is_encoder_decoder": False}
    )
    orders = {stage["stage_id"]: stage["order"] for stage in semantic["stages"]}

    assert topological_node_ids(graph)[0] == "graph-input"
    assert all(orders[edge["source_stage_id"]] < orders[edge["target_stage_id"]] for edge in semantic["stage_edges"])


def test_tensor_journey_never_labels_an_ambiguous_route_exact() -> None:
    model = nn.ReLU().eval()
    graph = trace_model(model, (torch.zeros(1, 3),), {}, "ambiguous")["graph"]
    for edge in graph["edges"]:
        edge["confidence"] = "ambiguous"

    semantic = generate_semantics(
        _version(model, "ambiguous"), graph, generated_at="2026-08-12T00:00:00Z", config={"is_encoder_decoder": False}
    )

    assert semantic["journeys"][0]["route_confidence"] == "ambiguous"
    assert any(step["route_confidence"] == "ambiguous" for step in semantic["journeys"][0]["steps"][1:])


def test_fixed_registry_contains_only_the_v1_vocabulary() -> None:
    assert {item["id"] for item in load_registry()["tags"]} == {
        "input",
        "embedding_or_projection",
        "position_or_context",
        "attention_or_mixer",
        "feed_forward",
        "normalization_or_residual",
        "aggregation_or_decoder",
        "output_or_head",
        "other",
    }


def test_architecture_rule_packs_require_exact_config_architecture_ids() -> None:
    model = nn.ReLU().eval()
    graph = trace_model(model, (torch.zeros(1, 3),), {}, "packs")["graph"]
    version = _version(model, "packs")

    bert = generate_semantics(
        version,
        graph,
        generated_at="2026-08-12T00:00:00Z",
        config={"model_type": "bert", "is_encoder_decoder": False},
    )
    causal = generate_semantics(
        version,
        graph,
        generated_at="2026-08-12T00:00:00Z",
        config={"model_type": "apertus", "is_encoder_decoder": False},
    )
    vision = generate_semantics(
        {**version, "task_type": "vision"},
        graph,
        generated_at="2026-08-12T00:00:00Z",
        config={"model_type": "dinov3_vit", "is_encoder_decoder": False},
    )

    assert bert["rule_pack_ids"] == []
    assert causal["rule_pack_ids"] == ["causal-language-decoder"]
    assert vision["rule_pack_ids"] == ["vision-encoder"]


def test_semantic_contracts_are_published_from_canonical_sources(tmp_path: Path) -> None:
    refs = publish_semantic_contracts(tmp_path)

    assert refs == {
        "semantic_schema_ref": SEMANTIC_SCHEMA_REF,
        "interface_tags_ref": INTERFACE_TAGS_REF,
    }
    assert json.loads((tmp_path / INTERFACE_TAGS_REF).read_text()) == load_registry()
    assert json.loads((tmp_path / SEMANTIC_SCHEMA_REF).read_text()) == json.loads(
        Path("src/schemas/semantic-model.v1.schema.json").read_text()
    )


def test_semantic_report_distinguishes_passed_fallback_partial_failed_and_unselected() -> None:
    coverage = {"module_stage_fraction": 1.0}
    entries = [
        {"version_id": "alpha", "semantic_ref": "semantics/alpha.json", "generation_status": "passed", "coverage": coverage},
        {"version_id": "beta", "semantic_ref": "semantics/beta.json", "generation_status": "fallback", "coverage": coverage},
        {"version_id": "charlie", "semantic_ref": "semantics/charlie.json", "generation_status": "partial", "coverage": coverage},
    ]

    report = semantic_report_document(
        entries,
        generated_at="2026-08-15T00:00:00+00:00",
        catalog_family_count=563,
        catalog_version_count=567,
        selected_family_count=4,
        selected_version_count=4,
        generated_family_count=3,
        failures=[{"version_id": "delta", "error_type": "TraceError", "message": "fixture failure"}],
    )

    assert report["generator_version"] == SEMANTIC_GENERATOR_VERSION
    assert report["counts"] == {"passed": 1, "fallback": 1, "partial": 1, "failed": 1}
    assert report["catalog"]["generated_family_fraction"] == round(3 / 563, 6)
    assert report["catalog"]["generated_version_fraction"] == round(3 / 567, 6)
    assert report["remaining_reasons"] == [
        {"reason": "outside_selected_build_scope", "family_count": 559, "version_count": 563},
        {"reason": "build_failed", "family_count": 1, "version_count": 1},
    ]
    assert report["models"][-1]["reason"] == "TraceError"
