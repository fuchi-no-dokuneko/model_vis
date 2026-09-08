"""Describe one operation using its own ports, including branch inputs."""


def operation_facts(node, edges):
    inputs, outputs = node.get("input_ports", []), node.get("output_ports", [])
    before = [port.get("shape", []) for port in inputs]
    after = [port.get("shape", []) for port in outputs]
    if not inputs:
        explanation = f"Model input exposes {after}."
    elif not outputs:
        explanation = f"Model output receives {before}."
    elif before == after:
        explanation = f"Shape is preserved: {before} → {after}."
    else:
        explanation = f"This operation transforms {before} → {after}."
    fields = ("port_id", "tensor_id", "name", "shape", "dtype")
    return {
        "input_ports": [{k: p[k] for k in fields if k in p} for p in inputs],
        "output_ports": [{k: p[k] for k in fields if k in p} for p in outputs],
        "producer_node_ids": sorted({e["source"] for e in edges if e["target"] == node["id"]}),
        "consumer_node_ids": sorted({e["target"] for e in edges if e["source"] == node["id"]}),
        "explanation": explanation,
    }
