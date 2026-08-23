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

test("safe rectangles and edge intervals cover every overlay side", () => {
  assert.deepEqual(graphSafeRect({}, [null, { width: 0, height: 10 }], 0), {
    left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0,
    insets: { left: 0, top: 0, right: 0, bottom: 0 },
  });
  const viewport = { width: 1000, height: 600 };
  const overlays = {
    left: { left: 0, top: 200, right: 100, bottom: 300, width: 100, height: 100 },
    top: { left: 400, top: 0, right: 500, bottom: 80, width: 100, height: 80 },
    right: { left: 900, top: 200, right: 1000, bottom: 300, width: 100, height: 100 },
    bottom: { left: 400, top: 520, right: 500, bottom: 600, width: 100, height: 80 },
  };
  assert.equal(graphSafeRect(viewport, [overlays.left]).left, 112);
  assert.equal(graphSafeRect(viewport, [overlays.top]).top, 92);
  assert.equal(graphSafeRect(viewport, [overlays.right]).right, 888);
  assert.equal(graphSafeRect(viewport, [overlays.bottom]).bottom, 508);

  const rectangles = Object.values(overlays).map((value) => ({
    ...value, viewportWidth: viewport.width, viewportHeight: viewport.height,
  }));
  for (const side of ["left", "right", "top", "bottom"]) {
    const intervals = intervalsForEdge(rectangles, side, 120, side === "left" || side === "right" ? 600 : 1000);
    assert.equal(intervals.length, 1);
  }
});

test("marker placement reports items that cannot fit", () => {
  const result = placeMarkers1D(
    [{ id: "late", desired: 90 }, { id: "early", desired: 5 }],
    60,
    30,
    [{ start: 0, end: 40 }],
    8,
    4,
  );
  assert.equal(result.placements.length, 0);
  assert.deepEqual(result.overflow.map((item) => item.id).sort(), ["early", "late"]);
});

test("operation projection handles absent graphs, root fallbacks, and both scope boundaries", () => {
  assert.deepEqual(operationProjection(null), { nodes: [], edges: [], layerGroups: [] });
  const graph = canonicalGraph();
  graph.modules[0].module_id = "module-00000";
  for (const node of graph.nodes.filter((node) => node.module_id === "root")) node.module_id = "module-00000";
  const root = operationProjection(graph, "missing");
  assert.equal(root.nodes.length, graph.nodes.length);

  const scopedGraph = canonicalGraph();
  scopedGraph.nodes.find((node) => node.id === "q").input_ports.push(port("q", "input", 1, "peer", "tk"));
  scopedGraph.edges.push({
    edge_id: "k-q", source: "k", source_port: "k:out:0", target: "q", target_port: "q:in:1",
    tensor_id: "tk", shape: [1, 4], confidence: "exact",
  });
  const scoped = operationProjection(scopedGraph, "qmod");
  assert.ok(scoped.nodes.some((node) => node.kind === "scope_input"));
  assert.ok(scoped.nodes.some((node) => node.kind === "scope_output"));
  assert.ok(scoped.edges.some((edge) => edge.source.startsWith("scope_input:")));
  assert.ok(scoped.edges.some((edge) => edge.target.startsWith("scope_output:")));
});

test("module projection handles empty input, module calls, parameters, and duplicate tensors", () => {
  assert.deepEqual(moduleProjection(null), { nodes: [], edges: [], layerGroups: [] });
  const graph = canonicalGraph();
  graph.nodes.push({
    id: "weight", kind: "parameter", name: "weight", module_id: "qmod", module_path: "layer.0.query",
    input_ports: [], output_ports: [port("weight", "output", 0, "weight", "tw")], source_ref: {},
  });
  graph.edges.push({
    edge_id: "weight-q", source: "weight", source_port: "weight:out:0", target: "q", target_port: "q:in:1",
    tensor_id: "tw", shape: [4, 4], confidence: "exact",
  });
  graph.module_calls = [{
    module_id: "qmod",
    input_ports: [port("call-q", "input", 0, "hidden", "t0")],
    output_ports: [port("call-q", "output", 0, "result", "tq")],
  }];
  graph.layer_groups = [];
  for (const node of graph.nodes) node.layer_group_id = null;
  graph.edges.push({ ...graph.edges[0], edge_id: "duplicate-input" });
  const result = moduleProjection(graph, "layer");

  assert.ok(result.nodes.length);
  assert.equal(new Set(result.edges.map((edge) => `${edge.source}:${edge.target}:${edge.tensor_id}`)).size, result.edges.length);
  assert.ok(result.nodes.some((node) => node.outputPorts.some((value) => value.name === "result")));
});

test("block projection rejects empty input and deduplicates self and repeated routes", () => {
  assert.deepEqual(blocksProjection(null, null), { nodes: [], edges: [], layerGroups: [] });
  assert.deepEqual(blocksProjection(canonicalGraph(), { blocks: [] }), { nodes: [], edges: [], layerGroups: [] });
  const sharedOutput = port("one", "output", 0, "output", "shared");
  const sharedInput = port("two", "input", 0, "input", "shared");
  const document = { blocks: [
    { block_uid: "one", block_type: "a", qualified_name: "one", output_ports: [sharedOutput], input_ports: [port("one", "input", 0, "self", "shared")] },
    { block_uid: "two", block_type: "b", qualified_name: "two", output_ports: [], input_ports: [sharedInput, { ...sharedInput, port_id: "two:in:1" }] },
  ] };
  const result = blocksProjection(canonicalGraph(), document);
  assert.equal(result.edges.length, 1);
  assert.deepEqual(result.edges[0].shape, [1, 4]);
});

test("architecture projection covers source, both, missing tensor, and invalid edges", () => {
  assert.deepEqual(architectureProjection(null, null), { nodes: [], edges: [], layerGroups: [] });
  const graph = canonicalGraph();
  graph.tensors = [{ tensor_id: "t0", shape: [1, 4], dtype: "torch.float16", device: "cpu" }];
  const semantic = {
    stages: [
      { stage_id: "one", stage_type: "input", semantic_name: "Input", tags: ["input"], module_ids: ["missing"], input_tensor_ids: [], output_tensor_ids: ["t0", "unknown"] },
      { stage_id: "two", stage_type: "output", semantic_name: "Output", tags: ["output"], module_ids: [], input_tensor_ids: ["t0", "unknown"], output_tensor_ids: [] },
    ],
    stage_edges: [
      { source_stage_id: "one", target_stage_id: "two", tensor_ids: ["t0"], confidence: "exact" },
      { source_stage_id: "one", target_stage_id: "two", tensor_ids: ["unknown"], confidence: "exact" },
      { source_stage_id: "missing", target_stage_id: "two", tensor_ids: ["t0"], confidence: "inferred" },
    ],
  };
  const source = architectureProjection(graph, semantic, "source");
  const both = architectureProjection(graph, semantic, "both");
  assert.equal(source.nodes[0].title, "input");
  assert.match(both.nodes[0].subtitle, /input/);
  assert.equal(source.nodes[0].outputPorts[1].dtype, "unknown");
  assert.equal(source.edges.length, 2);
  assert.deepEqual(source.edges[1].shape, []);
  assert.equal(architectureProjection({ ...graph, tensors: undefined }, semantic).nodes.length, 2);
});

test("project dispatch and route parser cover fallbacks and failures", () => {
  assert.deepEqual(projectGraph({}), { nodes: [], edges: [], layerGroups: [] });
  const graph = canonicalGraph();
  const fallbackFamily = projectGraph({ mode: "family", current, index: [] });
  assert.deepEqual(fallbackFamily.nodes[1].raw.parameters, { total: 32 });
  assert.equal(projectGraph({ mode: "operation", current, graph }).nodes.length, graph.nodes.length);
  assert.ok(projectGraph({ mode: "module", current, graph }).nodes.length);
  assert.deepEqual(projectGraph({ mode: "blocks", current, graph, blocks: null }).nodes, []);
  assert.deepEqual(projectGraph({ mode: "architecture", current, graph, semantic: null }).nodes, []);

  assert.deepEqual(parseViewerRoute(""), {});
  assert.deepEqual(parseViewerRoute("https://host/#/version/tiny%20model"), { version: "tiny model" });
  assert.throws(() => parseViewerRoute("#/compare/only-one"), /requires two/);
  assert.throws(() => parseViewerRoute("#/unknown/value"), /Invalid route/);
});

test("layout and bounds cover empty, invalid, cyclic, and default geometry", () => {
  assert.equal(layoutGraph([], []).size, 0);
  const nodes = [
    { id: "a", title: "A", raw: { module_path: "z" } },
    { id: "b", title: "B", raw: { module_path: "a" } },
    { id: "orphan", title: "Orphan" },
  ];
  const positions = layoutGraph(nodes, [
    { source: "missing", target: "a" },
    { source: "a", target: "a" },
    { source: "a", target: "b" },
    { source: "b", target: "a" },
  ]);
  assert.equal(positions.size, 3);
  assert.ok(positions.get("a").y !== positions.get("b").y);
  assert.deepEqual(graphBounds([{ id: "missing" }], new Map()), { width: 400, height: 300 });
  assert.deepEqual(graphBounds([], new Map()), { width: 400, height: 300 });
});

test("semantic labels cover source identity and shape fallbacks", () => {
  const graph = {
    nodes: [
      {
        id: "semantic-id", kind: "aten_op", module_id: "module-a", module_path: "",
        display_name: "Display A", name: "Name A", inputs: [{ shape: [1, 2] }], outputs: [null, [2, 3], { shape: [1, 3] }],
      },
      {
        id: "module-entity", kind: "aten_op", module_id: "module-b", module_path: "module.b",
        qualified_name: "module.b", input_ports: [], output_ports: [], name: "Name B",
      },
      {
        id: "source-only", kind: "aten_op", module_id: "module-c", module_path: "",
        input_ports: [], output_ports: [], name: "Name C",
      },
      { id: "display-only", kind: "aten_op", module_id: "module-d", module_path: "", input_ports: [], output_ports: [], display_name: "Display D" },
      { id: "id-only", kind: "aten_op", module_id: "module-e", module_path: "", input_ports: [], output_ports: [] },
    ],
    edges: [],
    modules: [{ module_id: "module-00000", qualified_name: "<root>" }],
    layer_groups: [],
  };
  const semantic = { entities: {
    "semantic-id": { semantic_name: "", primary_tag: "attention_or_mixer", source_name: "Entity A" },
    "module-b": { semantic_name: "Semantic B", primary_tag: "other", qualified_name: "Qualified B" },
    "source-only": {},
  } };
  const semanticResult = projectGraph({ mode: "operation", current, graph, semantic, labelMode: "semantic" });
  const bothResult = projectGraph({ mode: "operation", current, graph, semantic, labelMode: "both" });
  const sourceResult = projectGraph({ mode: "operation", current, graph, semantic, labelMode: "source" });

  assert.equal(semanticResult.nodes.find((node) => node.id === "semantic-id").title, "attention or mixer");
  assert.equal(semanticResult.nodes.find((node) => node.id === "module-entity").title, "Semantic B");
  assert.equal(bothResult.nodes.find((node) => node.id === "semantic-id").subtitle, "Entity A");
  assert.equal(sourceResult.nodes.find((node) => node.id === "semantic-id").subtitle, "[2, 3] [1, 3]");
  assert.equal(sourceResult.nodes.find((node) => node.id === "source-only").title, "Name C");
  assert.equal(sourceResult.nodes.find((node) => node.id === "display-only").title, "Display D");
  assert.equal(sourceResult.nodes.find((node) => node.id === "id-only").title, "id-only");
  assert.equal(semanticResult.nodes.find((node) => node.id === "source-only").title, "Name C");
});

test("projection fallbacks retain incomplete external and grouped records", () => {
  const graph = canonicalGraph();
  graph.nodes.find((node) => node.id === "q").input_ports.push({
    port_id: "q:in:missing", direction: "input", index: 1, name: "", tensor_id: "", shape: [],
  });
  graph.edges.push({
    edge_id: "missing-q", source: "not-published", source_port: null, target: "q", target_port: "not-found",
    tensor_id: "", shape: [], confidence: "unresolved",
  });
  const scoped = operationProjection(graph, "qmod");
  const boundary = scoped.nodes.find((node) => node.kind === "scope_input" && node.raw.attributes.external_node_id === null);
  assert.equal(boundary.title, "From external graph");
  assert.equal(boundary.outputPorts[0].name, "scope input");

  const grouped = canonicalGraph();
  grouped.layer_groups = [{ layer_group_id: "missing-group", module_id: "not-a-module", qualified_name: "layer.missing", color_index: 1 }];
  const query = grouped.nodes.find((node) => node.id === "q");
  query.layer_group_id = "missing-group";
  query.module_path = "layer.missing.query";
  const groupedResult = moduleProjection(grouped);
  assert.ok(groupedResult.nodes.some((node) => node.id === "group:not-a-module"));
});

test("remaining projection defaults cover absent ports, shapes, summaries, and duplicate layout IDs", () => {
  const graph = canonicalGraph();
  const document = { blocks: [
    { block_uid: "source", block_type: "a", qualified_name: "source", output_ports: [{ port_id: "source:out:0", tensor_id: "x" }] },
    { block_uid: "target", block_type: "b", qualified_name: "target", input_ports: [{ port_id: "target:in:0", tensor_id: "x", shape: [2] }] },
    { block_uid: "empty", block_type: "c", qualified_name: "empty" },
  ] };
  assert.deepEqual(blocksProjection(graph, document).edges[0].shape, [2]);
  document.blocks[1].input_ports[0].shape = null;
  assert.deepEqual(blocksProjection(graph, document).edges[0].shape, []);

  const family = projectGraph({
    mode: "family",
    current,
    family: { versions: ["summary"] },
    index: [{ version_id: "summary" }],
  });
  assert.equal(family.nodes[1].raw.name, "Tiny");
  assert.equal(family.nodes[1].raw.parameters, 32);

  const duplicates = [{ id: "same", title: "First" }, { id: "same", title: "Second" }];
  assert.equal(layoutGraph(duplicates, []).size, 1);
  assert.deepEqual(graphBounds([{ id: "default" }], new Map([["default", { x: 10, y: 20 }]])), {
    width: 400, height: 300,
  });
});
