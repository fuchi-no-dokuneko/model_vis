from src.model_builder.staged import detect_layer_variants, plan_trace


def test_detects_schedule_and_late_moe_as_distinct_variants() -> None:
    variants = detect_layer_variants({
        "num_hidden_layers": 6,
        "layers_block_type": ["attention", "attention", "attention", "attention", "attention", "attention"],
        "first_k_dense_replace": 3,
        "moe_layer_freq": 1,
        "n_routed_experts": 8,
    })
    assert len(variants) == 2
    assert variants[0]["effective_config"]["feed_forward_role"] == "dense"
    assert variants[0]["layer_indices"] == [0, 1, 2]
    assert variants[1]["effective_config"]["feed_forward_role"] == "moe"
    assert variants[1]["layer_indices"] == [3, 4, 5]


def test_resource_preflight_uses_full_forward_only_when_model_fits() -> None:
    resources = {"total_memory_bytes": 16 * 1024**3, "available_memory_bytes": 15 * 1024**3, "cpu_count": 6}
    small = plan_trace({
        "hidden_size": 64, "intermediate_size": 128, "vocab_size": 256,
        "num_hidden_layers": 2, "num_attention_heads": 4,
    }, resources)
    large = plan_trace({
        "hidden_size": 7168, "intermediate_size": 18432, "vocab_size": 129280,
        "num_hidden_layers": 61, "num_attention_heads": 128,
        "first_k_dense_replace": 3, "n_routed_experts": 256, "moe_intermediate_size": 2048,
    }, resources)
    assert small["execution_mode"] == "full_model_forward"
    assert large["execution_mode"] == "unique_structure_forward"
    assert len(large["templates"]) == 2
