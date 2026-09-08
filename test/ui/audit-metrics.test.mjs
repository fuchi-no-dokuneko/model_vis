import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { metricDifference } from "../../src/ui/comparison-metrics.js";
import { parseViewerRoute } from "../../src/ui/graph-model.js";

const version = (id) => JSON.parse(readFileSync(`model_code/versions/${id}.json`));

test("comparison distinguishes missing, equal, different and incompatible real model metrics", () => {
  const unknown = version("afmoe").parameter_evidence.parameter_count;
  const bert = version("bert").parameter_evidence.parameter_count;
  const arcee = version("arcee").parameter_evidence.parameter_count;
  assert.equal(metricDifference(unknown, unknown), "Unavailable for both");
  assert.equal(metricDifference(unknown, bert), "Not comparable");
  assert.equal(metricDifference(bert, bert), "0");
  assert.match(metricDifference(bert, arcee), /^\+/);
  assert.equal(metricDifference(bert, arcee, false), "Not comparable: scopes differ");
});

test("all compare pairs and views round trip; the audited Window route is rejected", () => {
  for (const pair of [["afmoe", "aimv2"], ["bert", "bertjapanese"], ["apertus", "arcee"]]) {
    for (const view of ["architecture", "family", "module", "blocks", "operation"]) {
      const route = parseViewerRoute(`modelvis:/compare/${pair.join("/")}/view/${view}/detail/standard/labels/both`);
      assert.deepEqual(route.compare, pair); assert.equal(route.view, view);
    }
  }
  assert.throws(() => parseViewerRoute("#/compare/afmoe/aimv2/view/%5Bobject%20Window%5D"), /Unknown view/);
});
