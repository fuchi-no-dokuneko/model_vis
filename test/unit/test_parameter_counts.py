from copy import deepcopy
from pathlib import Path

import pytest

from src.model_builder.parameter_counts import _count, parameter_evidence
from src.model_builder.util import read_json

ROOT = Path(__file__).parents[2] / "model_code"


@pytest.mark.parametrize("version_id,total,head_total", [
    ("bert", 109_482_240, 109_514_298),
    ("arcee", 4_291_496_960, 4_619_189_760),
])
def test_pinned_backbone_and_head_counts(version_id, total, head_total):
    version = read_json(ROOT / f"versions/{version_id}.json")
    evidence = parameter_evidence(ROOT, version, read_json(ROOT / version["graph_ref"]))
    assert evidence["parameter_count"] == total
    assert evidence["variants"][0]["parameter_count"] == head_total
    assert evidence["revision"] == version["official_config_source"]["revision"]
    assert evidence["publisher_parameter_count"] is None


@pytest.mark.parametrize("tied,bias", [(False, False), (True, False), (False, True), (True, True)])
def test_compact_gqa_non_gated_mlp_biases_and_tied_head(tied, bias):
    config = dict(model_type="arcee", vocab_size=37, hidden_size=16, intermediate_size=24,
                  num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                  head_dim=4, attention_bias=bias, mlp_bias=bias, tie_word_embeddings=tied,
                  bos_token_id=1, eos_token_id=2)
    before = deepcopy(config)
    # Independent shape arithmetic: Q/K/V/O + up/down MLP + two RMS norms.
    attention = 16 * (16 + 8 + 8 + 16) + (16 + 8 + 8 + 16) * bias
    mlp = 2 * 16 * 24 + (24 + 16) * bias
    backbone = 37 * 16 + 2 * (attention + mlp + 2 * 16) + 16
    assert _count("transformers.ArceeModel", config) == backbone
    assert _count("transformers.ArceeForCausalLM", config) == backbone + (0 if tied else 37 * 16)
    assert config == before


@pytest.mark.parametrize("version_id", ["bertjapanese", "mamba2"])
def test_unmapped_alias_and_native_config_do_not_claim_exact_counts(version_id):
    version = read_json(ROOT / f"versions/{version_id}.json")
    evidence = parameter_evidence(ROOT, version, read_json(ROOT / version["graph_ref"]))
    assert evidence["parameter_count"] is None
    assert evidence["status"] == "unavailable"
