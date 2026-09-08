import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { projectGraph } from "../../src/ui/graph-model.js";
import { overviewLayout } from "../../src/ui/overview-layout.js";

const read = (ref) => JSON.parse(readFileSync(`model_code/${ref}`));
test("fitted CLIP and VAE overviews conserve nodes and observed cross-group routes without intersections", () => {
  for (const [id, mode] of [["clip", "architecture"], ["autoencoderklkvae", "operation"]]) {
    const current = read(`versions/${id}.json`), graph = read(current.graph_ref), semantic = read(current.semantic_ref);
    const view = projectGraph({ mode, current, graph, semantic, labelMode: "both" });
    for (const width of [300, 600, 1000]) {
      const safe = { left: 12, top: 42, width, height: 420 };
      const { placements, edges } = overviewLayout(view, semantic, safe);
      const allIds = placements.flatMap((group) => group.items.map((item) => item.id));
      assert.equal(new Set(allIds).size, view.nodes.length);
      const owners = new Map();
      placements.forEach((group, index) => {
        group.items.forEach((item) => owners.set(item.id, index));
        assert.ok(group.x >= safe.left && group.x + 100 <= safe.left + safe.width);
        assert.ok(group.y >= safe.top && group.y + 44 <= safe.top + safe.height);
        for (const other of placements.slice(index + 1)) assert.ok(Math.abs(group.x - other.x) >= 100 || Math.abs(group.y - other.y) >= 44);
      });
      const cross = view.edges.filter((edge) => owners.get(edge.source) !== owners.get(edge.target));
      assert.equal(edges.reduce((sum, edge) => sum + edge.tensorIds.length, 0), cross.length);
    }
  }
});
