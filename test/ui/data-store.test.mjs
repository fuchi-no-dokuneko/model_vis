import assert from "node:assert/strict";
import test from "node:test";

import { configDifferences, ModelStore } from "../../src/ui/data-store.js";

test("model store caches assets and loads traces only when requested", async () => {
  const calls = [];
  const assets = {
    "model_code/manifest.v2.json": { search_index: "indexes/search.v2.json" },
    "model_code/indexes/search.v2.json": [{ version_id: "tiny" }],
    "model_code/versions/tiny.json": { version_id: "tiny", trace_ref: "traces/tiny.json" },
    "model_code/traces/tiny.json": { operations: [] },
  };
  const fetcher = async (path) => {
    calls.push(path);
    return { ok: path in assets, status: path in assets ? 200 : 404, json: async () => assets[path] };
  };
  const store = new ModelStore("model_code", fetcher);
  await store.initialize();
  const version = await store.version("tiny");
  await store.version("tiny");

  assert.equal(calls.filter((path) => path.endsWith("versions/tiny.json")).length, 1);
  assert.equal(calls.some((path) => path.includes("traces/")), false);

  await store.trace(version);
  assert.equal(calls.filter((path) => path.endsWith("traces/tiny.json")).length, 1);
});

test("config comparison reports only changed leaves", () => {
  const result = configDifferences(
    { hidden: 16, nested: { layers: 1, mode: "a" } },
    { hidden: 16, nested: { layers: 2, mode: "a" } },
  );
  assert.deepEqual(result, [{ key: "nested.layers", left: 1, right: 2 }]);
});

test("model store loads official, trace, and difference configs independently", async () => {
  const assets = {
    "model_code/configs/official/tiny.json": { hidden: 64 },
    "model_code/configs/trace/tiny.json": { config: { hidden: 16 } },
    "model_code/configs/diffs/tiny.json": { differences: [{ path: "hidden" }] },
  };
  const store = new ModelStore("model_code", async (path) => ({
    ok: path in assets,
    status: path in assets ? 200 : 404,
    json: async () => assets[path],
  }));
  const version = {
    official_config_ref: "configs/official/tiny.json",
    trace_config_ref: "configs/trace/tiny.json",
    config_diff_ref: "configs/diffs/tiny.json",
  };
  assert.equal((await store.officialConfig(version)).hidden, 64);
  assert.equal((await store.traceConfig(version)).config.hidden, 16);
  assert.equal((await store.configDiff(version)).differences[0].path, "hidden");
});
