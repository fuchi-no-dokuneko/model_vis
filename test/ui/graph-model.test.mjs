import assert from "node:assert/strict";
import test from "node:test";

import { layoutGraph, projectGraph } from "../../src/ui/graph-model.js";

const current = {
  family_id: "tiny",
  family_name: "Tiny",
  version_id: "tiny-v1",
  parameters: { total: 32 },
  entrypoint_class: "TinyModel",
};

test("family projection includes family and version hierarchy", () => {
  const result = projectGraph({
    mode: "family",
    current,
    family: { versions: ["tiny-v1"] },
    index: [{ version_id: "tiny-v1", family_name: "Tiny", parameters: 32 }],
  });
  assert.equal(result.nodes.length, 2);
  assert.deepEqual(result.edges, [{ source: "family:tiny", target: "version:tiny-v1" }]);
});

test("collapsed and expanded version projections retain distinct detail levels", () => {
  const trace = { operations: [
    { op_id: "op-1", kind: "module_call", display_name: "Linear", outputs: [{ shape: [1, 4] }] },
    { op_id: "fn-1", kind: "torch_function", display_name: "relu", outputs: [{ shape: [1, 4] }] },
  ] };
  const graph = {
    nodes: [
      { id: "tv-0", name: "Linear", kind: "ModuleNode", depth: 1, output_shapes: [[1, 4]] },
      { id: "tv-1", name: "linear", kind: "FunctionNode", depth: 2, output_shapes: [[1, 4]] },
    ],
    edges: [],
  };
  const collapsed = projectGraph({ mode: "version", current, trace, graph, expanded: false });
  const expanded = projectGraph({ mode: "version", current, trace, graph, expanded: true });
  assert.deepEqual(collapsed.nodes.map((node) => node.id), ["tv-0"]);
  assert.deepEqual(expanded.nodes.map((node) => node.id), ["tv-0", "tv-1"]);
});

test("layout is stable and follows edge rank", () => {
  const nodes = [{ id: "a" }, { id: "b" }, { id: "c" }];
  const edges = [{ source: "a", target: "b" }, { source: "b", target: "c" }];
  const first = layoutGraph(nodes, edges);
  const second = layoutGraph(nodes, edges);
  assert.deepEqual([...first], [...second]);
  assert.ok(first.get("a").y < first.get("b").y);
  assert.ok(first.get("b").y < first.get("c").y);
});

test("collapsed version falls back to function nodes when modules are hidden", () => {
  const graph = {
    nodes: [
      { id: "tensor", name: "input", kind: "TensorNode", output_shapes: [[1, 4]] },
      { id: "function", name: "linear", kind: "FunctionNode", output_shapes: [[1, 4]] },
    ],
    edges: [{ source: "tensor", target: "function" }],
  };
  const result = projectGraph({ mode: "version", current, graph, expanded: false });
  assert.deepEqual(result.nodes.map((node) => node.id), ["function"]);
});
