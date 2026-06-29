import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("static viewer has no runtime backend or dynamic code execution", async () => {
  const app = await readFile("src/ui/app.js", "utf8");
  const store = await readFile("src/ui/data-store.js", "utf8");
  const html = await readFile("src/ui/index.html", "utf8");

  assert.equal(`${app}${store}`.includes("eval("), false);
  assert.equal(`${app}${store}`.includes("from_pretrained"), false);
  assert.equal(/https?:\/\//.test(html), false);
  assert.match(store, /manifest\.v1\.json/);
  assert.match(store, /base = "model_code"/);
});

test("viewer exposes every required mode", async () => {
  const html = await readFile("src/ui/index.html", "utf8");
  for (const mode of ["family", "version", "block", "source"]) {
    assert.match(html, new RegExp(`data-mode="${mode}"`));
  }
});

test("viewer exposes required inspector and graph controls", async () => {
  const html = await readFile("src/ui/index.html", "utf8");
  for (const id of [
    "model-list", "graph-viewport", "inspector", "source-panel", "shapes-panel",
    "compare-pane", "density-button", "fit-button", "reset-button", "minimap",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
});
