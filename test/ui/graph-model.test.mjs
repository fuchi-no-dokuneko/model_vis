import assert from "node:assert/strict";
import test from "node:test";

import {
  architectureProjection, blocksProjection, graphBounds, graphSafeRect, intervalsForEdge, layoutGraph,
  moduleProjection, operationProjection, parseViewerRoute, placeMarkers1D, projectGraph,
  semanticZoomTier, tracePath,
} from "../../src/ui/graph-model.js";

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

test("architecture projection uses generated stages and exact boundary tensors", () => {
  const graph = canonicalGraph();
  graph.tensors = ["t0", "t1"].map((tensor_id) => ({ tensor_id, shape: [1, 4], dtype: "torch.float32", device: "cpu" }));
  const semantic = {
    stages: [
      { stage_id: "stage-input", stage_type: "input_adapter", semantic_name: "Model input", tags: ["input"], module_ids: ["root"], operation_ids: [], input_tensor_ids: [], output_tensor_ids: ["t0"] },
      { stage_id: "stage-output", stage_type: "output_adapter", semantic_name: "Model output", tags: ["output_or_head"], module_ids: ["root"], operation_ids: [], input_tensor_ids: ["t0"], output_tensor_ids: [] },
    ],
    stage_edges: [{ source_stage_id: "stage-input", target_stage_id: "stage-output", tensor_ids: ["t0"], confidence: "exact" }],
  };
  const result = architectureProjection(graph, semantic, "semantic");

  assert.deepEqual(result.nodes.map((node) => node.title), ["Model input", "Model output"]);
  assert.equal(result.edges[0].tensor_id, "t0");
  assert.equal(result.edges[0].source_port, "stage-input:out:0");
  assert.equal(result.edges[0].target_port, "stage-output:in:0");
});

test("explicit route parser supports nested stages, compare routes, and legacy routes", () => {
  assert.deepEqual(parseViewerRoute("#/version/dinov3/view/architecture/stage/stage-003"), {
    version: "dinov3", view: "architecture", stage: "stage-003",
  });
  assert.deepEqual(parseViewerRoute("#/compare/apertus/bert/view/architecture/detail/standard/labels/both"), {
    compare: ["apertus", "bert"], view: "architecture", detail: "standard", labels: "both",
  });
  assert.deepEqual(parseViewerRoute("modelvis:/version/bert/view/module/operation/op-1"), {
    version: "bert", view: "module", operation: "op-1",
  });
  assert.throws(() => parseViewerRoute("#/version/bert/unpaired"), /Invalid route segment/);
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

test("semantic zoom tiers use the amendment boundaries", () => {
  assert.equal(semanticZoomTier(0.16), "overview");
  assert.equal(semanticZoomTier(0.35), "compact");
  assert.equal(semanticZoomTier(0.69), "compact");
  assert.equal(semanticZoomTier(0.70), "normal");
});

test("safe graph rectangle reserves bottom overlays consistently", () => {
  const safe = graphSafeRect({ width: 1000, height: 700 }, [
    { left: 12, top: 590, right: 180, bottom: 688, width: 168, height: 98 },
    { left: 850, top: 590, right: 988, bottom: 688, width: 138, height: 98 },
  ]);
  assert.deepEqual({ left: safe.left, top: safe.top, right: safe.right, bottom: safe.bottom }, {
    left: 12, top: 12, right: 988, bottom: 578,
  });
});

test("continuation marker layout avoids reserved edge intervals and collisions", () => {
  const rectangles = [{
    left: 0, top: 40, right: 120, bottom: 100, width: 120, height: 60,
    viewportWidth: 800, viewportHeight: 500,
  }];
  const reserved = intervalsForEdge(rectangles, "left", 184, 500);
  const result = placeMarkers1D([
    { id: "a", desired: 50 },
    { id: "b", desired: 55 },
    { id: "c", desired: 120 },
  ], 500, 24, reserved, 8, 4);
  assert.equal(result.overflow.length, 0);
  assert.ok(result.placements[0].start >= 108);
  for (let index = 1; index < result.placements.length; index += 1) {
    assert.ok(result.placements[index].start - result.placements[index - 1].start >= 32);
  }
});
