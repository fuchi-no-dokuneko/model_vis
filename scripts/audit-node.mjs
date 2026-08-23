import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const lock = JSON.parse(await readFile(new URL("../package-lock.json", import.meta.url), "utf8"));
const installed = Object.keys(lock.packages ?? {}).filter((name) => name !== "");
assert.deepEqual(installed, [], "JavaScript packages require npm advisory review");
console.log(JSON.stringify({ passed: true, productionPackages: 0 }, null, 2));
