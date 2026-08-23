import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("static viewer has no runtime backend or dynamic code execution", async () => {
  const app = await readFile("src/ui/app.js", "utf8");
  const store = await readFile("src/ui/data-store.js", "utf8");
  const html = await readFile("src/ui/index.html", "utf8");

  assert.equal(`${app}${store}`.includes("eval("), false);
  assert.equal(app.includes("innerHTML"), false);
  assert.equal(`${app}${store}`.includes("from_pretrained"), false);
  assert.equal(/https?:\/\//.test(html), false);
  assert.match(store, /manifest\.v2\.json/);
  assert.match(store, /base = "model_code"/);
});

test("viewer exposes every required mode", async () => {
  const html = await readFile("src/ui/index.html", "utf8");
  for (const mode of ["architecture", "family", "module", "blocks", "operation"]) {
    assert.match(html, new RegExp(`data-mode="${mode}"`));
  }
});

test("viewer exposes required inspector and graph controls", async () => {
  const html = await readFile("src/ui/index.html", "utf8");
  for (const id of [
    "model-list", "module-tree", "source-tree", "uri-input", "graph-viewport", "inspector",
    "source-panel", "source-editor", "source-repository", "copy-source", "shapes-panel",
    "runtime-panel", "compare-pane", "density-button", "fit-button", "reset-button", "minimap",
    "graph-legend", "graph-search", "continuations", "structural-summary", "official-config-link",
    "theme-button", "detail-mode", "label-mode", "explain-panel", "explain-view",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
});

test("viewer keeps unsupported semantic models technically usable", async () => {
  const source = await readFile(new URL("../../src/ui/app.js", import.meta.url), "utf8");
  assert.match(source, /Semantic guide not yet available; showing technical structure\./);
  assert.match(source, /projectionMode = state\.mode === "architecture" && !state\.semantic \? "module"/);
});

test("static manifest publishes semantic contracts and generation report", async () => {
  const manifest = JSON.parse(await readFile("model_code/manifest.v2.json", "utf8"));
  assert.equal(manifest.semantic_index, "indexes/semantic.v1.json");
  assert.equal(manifest.semantic_report, "indexes/semantic-report.v1.json");
  assert.equal(manifest.semantic_generator_version, "1.0.0");
  assert.deepEqual(manifest.semantic_contracts, {
    schema_ref: "contracts/semantic-model.schema.json",
    interface_tags_ref: "contracts/interface-tags.v1.json",
  });

  const [schema, tags, index, report] = await Promise.all([
    readFile(`model_code/${manifest.semantic_contracts.schema_ref}`, "utf8").then(JSON.parse),
    readFile(`model_code/${manifest.semantic_contracts.interface_tags_ref}`, "utf8").then(JSON.parse),
    readFile(`model_code/${manifest.semantic_index}`, "utf8").then(JSON.parse),
    readFile(`model_code/${manifest.semantic_report}`, "utf8").then(JSON.parse),
  ]);
  assert.equal(schema.properties.generator_version.const, "1.0.0");
  assert.equal(tags.tags.length, 9);
  assert.equal(index.generated_at, manifest.semantic_generated_at);
  assert.equal(report.generated_at, manifest.semantic_generated_at);
  assert.equal(report.catalog.generated_version_count, manifest.versions.length);
  assert.equal(Object.values(report.counts).reduce((sum, count) => sum + count, 0), manifest.versions.length);
});
