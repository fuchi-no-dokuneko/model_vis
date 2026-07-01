import assert from "node:assert/strict";
import test from "node:test";

import { blocksProjection, graphBounds, layoutGraph, moduleProjection, operationProjection, projectGraph, tracePath } from "../../src/ui/graph-model.js";

const current = {
  family_id: "tiny",
  family_name: "Tiny",
  version_id: "tiny-v1",
  parameters: { total: 32 },
  entrypoint_class: "TinyModel",
};

function port(node, direction, index, name, tensor) {
  return {
    port_id: `${node}:${direction === "input" ? "in" : "out"}:${index}`,
    direction,
    index,
    name,
    tensor_id: tensor,
    shape: [1, 4],
    dtype: "torch.float32",
    device: "cpu",
  };
}

function canonicalGraph() {
  const input = { id: "input", kind: "graph_input", name: "Input", module_id: "root", module_path: "<root>", input_ports: [], output_ports: [port("input", "output", 0, "hidden", "t0")], source_ref: {} };
  const query = { id: "q", kind: "aten_op", name: "aten.linear", display_name: "linear", module_id: "qmod", module_path: "layer.0.query", layer_group_id: "layer0", input_ports: [port("q", "input", 0, "input", "t0")], output_ports: [port("q", "output", 0, "output", "tq")], source_ref: {} };
  const key = { id: "k", kind: "aten_op", name: "aten.linear", display_name: "linear", module_id: "kmod", module_path: "layer.0.key", layer_group_id: "layer0", input_ports: [port("k", "input", 0, "input", "t0")], output_ports: [port("k", "output", 0, "output", "tk")], source_ref: {} };
  const add = { id: "add", kind: "aten_op", name: "aten.add", display_name: "add", module_id: "layer", module_path: "layer.0", layer_group_id: "layer0", input_ports: [port("add", "input", 0, "query", "tq"), port("add", "input", 1, "residual", "t0")], output_ports: [port("add", "output", 0, "output", "t1")], source_ref: {} };
  const output = { id: "output", kind: "graph_output", name: "Output", module_id: "root", module_path: "<root>", input_ports: [port("output", "input", 0, "output", "t1")], output_ports: [], source_ref: {} };
  const edges = [
    ["input", "input:out:0", "q", "q:in:0", "t0"],
    ["input", "input:out:0", "k", "k:in:0", "t0"],
    ["q", "q:out:0", "add", "add:in:0", "tq"],
    ["input", "input:out:0", "add", "add:in:1", "t0"],
    ["add", "add:out:0", "output", "output:in:0", "t1"],
  ].map(([source, sourcePort, target, targetPort, tensor], index) => ({
    edge_id: `e${index}`, source, source_port: sourcePort, target, target_port: targetPort,
    tensor_id: tensor, shape: [1, 4], confidence: "exact",
  }));
  return {
    schema_version: "2.2.0",
    nodes: [input, query, key, add, output],
    edges,
    modules: [
      { module_id: "root", qualified_name: "<root>", display_name: "Tiny", parent_module_id: null, child_module_ids: ["layer"], layer_group_id: null },
      { module_id: "layer", qualified_name: "layer.0", display_name: "Layer", parent_module_id: "root", child_module_ids: ["qmod", "kmod"], layer_group_id: "layer0" },
      { module_id: "qmod", qualified_name: "layer.0.query", display_name: "Linear", parent_module_id: "layer", child_module_ids: [], layer_group_id: "layer0" },
      { module_id: "kmod", qualified_name: "layer.0.key", display_name: "Linear", parent_module_id: "layer", child_module_ids: [], layer_group_id: "layer0" },
    ],
    layer_groups: [{ layer_group_id: "layer0", module_id: "layer", qualified_name: "layer.0", color_index: 0 }],
  };
}

test("family projection includes family and version hierarchy", () => {
  const result = projectGraph({
    mode: "family",
    current,
    family: { versions: ["tiny-v1"] },
    index: [{ version_id: "tiny-v1", family_name: "Tiny", parameters: 32 }],
  });
  assert.equal(result.nodes.length, 2);
  assert.equal(result.edges[0].source, "family:tiny");
  assert.equal(result.edges[0].target, "version:tiny-v1");
});

test("operation projection preserves parallel fan-out and residual routes", () => {
  const result = operationProjection(canonicalGraph(), "root");
  assert.equal(result.edges.length, 5);
  assert.equal(result.edges.filter((edge) => edge.tensor_id === "t0").length, 3);
  assert.deepEqual(result.nodes.find((node) => node.id === "add").inputPorts.map((item) => item.name), ["query", "residual"]);
});

test("module projection derives groups from canonical edges without sequential synthesis", () => {
  const result = moduleProjection(canonicalGraph(), "layer");
  assert.ok(result.nodes.length >= 3);
  assert.ok(result.edges.length >= 2);
  assert.ok(result.edges.every((edge) => edge.tensor_id));
  assert.ok(result.edges.every((edge) => edge.edge_id.startsWith("group:")));
});

test("module projection collapses repeated fan-out into one boundary port and route", () => {
  const graph = canonicalGraph();
  const queryOperation = graph.nodes.find((node) => node.id === "q");
  const key = graph.nodes.find((node) => node.id === "k");
  queryOperation.layer_group_id = null;
  key.module_id = "qmod";
  key.module_path = "layer.0.query";
  key.layer_group_id = null;
  const result = moduleProjection(graph, "layer");
  const query = result.nodes.find((node) => node.raw.module_id === "qmod");
  assert.equal(query.inputPorts.filter((portValue) => portValue.tensor_id === "t0").length, 1);
  assert.equal(result.edges.filter((edge) => edge.target === query.id && edge.tensor_id === "t0").length, 1);
});

test("scoped operation projection creates explicit boundary ports", () => {
  const result = operationProjection(canonicalGraph(), "qmod");
  assert.ok(result.nodes.some((node) => node.kind === "scope_input" || node.kind === "graph_input"));
  assert.ok(result.nodes.some((node) => node.kind === "scope_output"));
  assert.ok(result.edges.every((edge) => edge.source_port && edge.target_port));
  const boundary = result.nodes.find((node) => node.kind === "scope_output");
  assert.match(boundary.title, /^To /);
  assert.ok(boundary.raw.attributes.external_module_path);
});

test("blocks projection exposes generated architectural blocks and exact tensor routes", () => {
  const blocks = { blocks: [
    { block_uid: "b1", block_type: "attention", qualified_name: "layer.attn", input_ports: [port("b1", "input", 0, "input", "t0")], output_ports: [port("b1", "output", 0, "query", "tq")] },
    { block_uid: "b2", block_type: "mlp", qualified_name: "layer.mlp", input_ports: [port("b2", "input", 0, "input", "tq")], output_ports: [port("b2", "output", 0, "output", "t1")] },
  ] };
  const result = blocksProjection(canonicalGraph(), blocks);
  assert.deepEqual(result.nodes.map((node) => node.kind), ["block_attention", "block_mlp"]);
  assert.equal(result.edges.length, 1);
  assert.equal(result.edges[0].tensor_id, "tq");
});

test("path tracing follows all upstream and downstream branches", () => {
  const graph = canonicalGraph();
  const upstream = tracePath(graph.edges, "add", "upstream");
  assert.deepEqual([...upstream.nodes].sort(), ["add", "input", "q"]);
  const isolated = tracePath(graph.edges, "q", "isolate");
  assert.ok(isolated.nodes.has("output"));
  assert.ok(isolated.nodes.has("input"));
});

test("collapse and expansion preserve scope-boundary tensor routes", () => {
  const detailed = operationProjection(canonicalGraph(), "qmod");
  const grouped = moduleProjection(canonicalGraph(), "qmod");
  const detailedTensors = [...new Set(detailed.edges.map((edge) => edge.tensor_id))].sort();
  const groupedTensors = [...new Set(grouped.edges.map((edge) => edge.tensor_id))].sort();
  assert.deepEqual(groupedTensors, detailedTensors);
});

test("layout is stable and follows edge rank", () => {
  const nodes = [{ id: "a", raw: {} }, { id: "b", raw: {} }, { id: "c", raw: {} }];
  const edges = [{ source: "a", target: "b" }, { source: "b", target: "c" }];
  const first = layoutGraph(nodes, edges);
  const second = layoutGraph(nodes, edges);
  assert.deepEqual([...first], [...second]);
  assert.ok(first.get("a").y < first.get("b").y);
  assert.ok(first.get("b").y < first.get("c").y);
});

test("graph bounds include persisted custom node dimensions", () => {
  const nodes = [{ id: "a" }];
  const positions = new Map([["a", { x: 120, y: 90 }]]);
  const sizes = new Map([["a", { width: 640, height: 420 }]]);
  assert.deepEqual(graphBounds(nodes, positions, sizes), { width: 840, height: 590 });
});
