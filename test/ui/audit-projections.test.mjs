import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseViewerRoute, projectGraph } from "../../src/ui/graph-model.js";

const read = (path) => JSON.parse(readFileSync(`model_code/${path}`));

test("real graph scopes retain technical identity and connected boundaries in every label mode", () => {
  for (const id of ["bit", "bert", "autoencoderklkvae"]) {
    const current = read(`versions/${id}.json`), graph = read(current.graph_ref), semantic = read(`semantics/${id}.json`);
    const scopes = [graph.modules[0], ...graph.modules.filter((m) => m.qualified_name.includes(".0."))].slice(0, 8);
    for (const scope of scopes) for (const mode of ["module", "operation"]) for (const labelMode of ["semantic", "both", "source"]) {
      const view = projectGraph({ mode, current, graph, semantic, labelMode, scopeModuleId: scope.module_id });
      const ids = new Set(view.nodes.map((node) => node.id));
      if (!view.nodes.length) assert.equal(graph.nodes.filter((n) => n.module_id === scope.module_id).length, 0);
      for (const edge of view.edges) { assert.ok(ids.has(edge.source)); assert.ok(ids.has(edge.target)); }
      for (const node of view.nodes) {
        assert.ok(node.title);
        const entity = semantic.entities[node.id];
        if (mode === "operation" && entity?.primary_tag === "other" && node.raw.display_name) assert.equal(node.title, node.raw.display_name);
      }
    }
  }
});

test("typed invalid professional preset and label names produce actionable route errors", () => {
  assert.throws(() => parseViewerRoute("modelvis:/version/bert/view/operation/detail/professional"), /Unknown detail mode/);
  assert.throws(() => parseViewerRoute("modelvis:/version/bert/view/operation/labels/technical"), /Unknown labels mode/);
});
