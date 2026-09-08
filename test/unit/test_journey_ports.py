from pathlib import Path

from src.model_builder.util import read_json

ROOT = Path(__file__).parents[2] / "model_code"


def test_every_published_journey_matches_its_own_operation_ports():
    total = 0
    for version_id in read_json(ROOT / "manifest.v2.json")["versions"]:
        version = read_json(ROOT / f"versions/{version_id}.json")
        graph = read_json(ROOT / version["graph_ref"])
        nodes = {node["id"]: node for node in graph["nodes"]}
        semantic = read_json(ROOT / version["semantic_ref"])
        for journey in semantic["journeys"]:
            for step in journey["steps"]:
                node = nodes[step["node_id"]]
                for direction in ["input_ports", "output_ports"]:
                    actual = step[direction]
                    expected = node[direction]
                    assert len(actual) == len(expected), (version_id, step["node_id"])
                    for left, right in zip(actual, expected):
                        assert left["tensor_id"] == right["tensor_id"]
                        assert left["shape"] == right["shape"]
                        assert left["dtype"] == right["dtype"]
                for name, target, source in [("producer_node_ids", "target", "source"), ("consumer_node_ids", "source", "target")]:
                    assert set(step[name]) == {edge[source] for edge in graph["edges"] if edge[target] == node["id"]}
                total += 1
    assert total > 5000


def test_bert_gelu_and_bit_padding_and_pooling_have_correct_math():
    expected = {"bert": {"gelu": (3072, 3072)}, "bit": {"pad": (8, 10), "max_pool2d": (10, 4)}}
    for version_id, operations in expected.items():
        semantic = read_json(ROOT / f"semantics/{version_id}.json")
        steps = semantic["journeys"][0]["steps"]
        for interface, (before, after) in operations.items():
            matches = [step for step in steps if interface in step["transform"]]
            assert matches, (version_id, interface)
            assert any(step["input_ports"][0]["shape"][-1] == before and step["output_ports"][0]["shape"][-1] == after for step in matches)
