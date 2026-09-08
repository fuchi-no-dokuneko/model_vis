import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { findOperations, operationRecords } from "../../src/ui/finder.js";
import { factsCsv, reviewFacts } from "../../src/ui/review-export.js";
import { subgraphSvg } from "../../src/ui/review-svg.js";

const read = (path) => JSON.parse(readFileSync(`model_code/${path}`));
const current = read("versions/bert.json"), graph = read(current.graph_ref);
const records = operationRecords(graph);

test("the finder combines real BERT operation, module, dtype, shape and tensor filters", () => {
  const gelu = findOperations(records, { interface: "gelu", module: "encoder.layer.0.", dtype: "float32", shape: "[3,5,3072]" });
  assert.equal(gelu.length, 1); assert.equal(gelu[0].id, "op-000028");
  const tensor = gelu[0].node.input_ports[0].tensor_id;
  assert.ok(findOperations(records, { tensor }).some((item) => item.id === gelu[0].id));
  assert.equal(findOperations(records, { query: "zzzz-no-such-operation" }).length, 0);
  assert.equal(findOperations(records, {}).length, graph.nodes.length);
});

test("tensor, dtype and shape filters describe the same observed port", () => {
  const embedding = records.find((r) => r.interface === "embedding");
  assert.ok(embedding);
  const integer = embedding.node.input_ports.find((p) => p.dtype === "torch.int64");
  const output = embedding.node.output_ports[0];
  assert.equal(findOperations([embedding], { tensor: integer.tensor_id, dtype: output.dtype }).length, 0);
  assert.equal(findOperations([embedding], { dtype: integer.dtype, shape: JSON.stringify(output.shape) }).length, 0);
  assert.equal(findOperations([embedding], { tensor: output.tensor_id, dtype: output.dtype, shape: JSON.stringify(output.shape) }).length, 1);
});

test("review exports preserve selected facts, branch boundaries, annotations and provenance", () => {
  const state = { current, graph, selectedIds: new Set(["op-000028"]), selectedId: "op-000028", mode: "operation", detailMode: "trace", labelMode: "source" };
  const annotation = 'GELU "preserves"\n3072 dimensions <verified shape>';
  const facts = reviewFacts(state, "https://localhost/#/version/bert/view/operation/operation/op-000028", annotation);
  assert.equal(facts.nodes.length, 1);
  assert.equal(facts.nodes[0].output_ports[0].shape.at(-1), 3072);
  assert.equal(facts.provenance.repo_id, "google-bert/bert-base-uncased");
  assert.ok(facts.boundary_edges.length >= 2);
  assert.match(factsCsv(facts), /""preserves""/);
  const svg = subgraphSvg(facts);
  assert.match(svg, /<svg xmlns=/); assert.match(svg, /&lt;verified shape>/);
  assert.equal(facts.annotation, annotation);
});
