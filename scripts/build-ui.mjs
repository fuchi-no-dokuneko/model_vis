import { cp, mkdir, readFile, readdir, rm, stat } from "node:fs/promises";
import path from "node:path";

function options(argv) {
  const result = { modelCode: "model_code", out: "build" };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--model-code") result.modelCode = argv[++i];
    else if (argv[i] === "--out") result.out = argv[++i];
  }
  return result;
}

async function files(root) {
  const output = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const target = path.join(root, entry.name);
    if (entry.isDirectory()) output.push(...await files(target));
    else output.push(target);
  }
  return output;
}

const config = options(process.argv.slice(2));
const manifestPath = path.join(config.modelCode, "manifest.v2.json");
await stat(manifestPath);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
if (manifest.schema_version !== "2.2.0") {
  throw new Error(`Unsupported generated-data schema: ${manifest.schema_version || "missing"}`);
}
const report = JSON.parse(await readFile(path.join(config.modelCode, manifest.build_report), "utf8"));
if (!["passed", "passed_with_warnings"].includes(report.status)
  || report.passed_version_count !== manifest.versions.length) {
  throw new Error("Generated model data did not pass its release build");
}
if (report.status === "passed_with_warnings") {
  const versions = await Promise.all(manifest.versions.map(async (versionId) => (
    JSON.parse(await readFile(path.join(config.modelCode, "versions", `${versionId}.json`), "utf8"))
  )));
  const partial = new Set(versions.filter((version) => version.status === "partial").map((version) => version.version_id));
  if (!report.warnings.length || report.warnings.some((warning) => !partial.has(warning.version_id))) {
    throw new Error("Release warnings are not attached to exact partial model records");
  }
}
await rm(config.out, { recursive: true, force: true });
await mkdir(config.out, { recursive: true });
await cp("src/ui", config.out, { recursive: true });
await cp(config.modelCode, path.join(config.out, "model_code"), { recursive: true });

const assets = await files(config.out);
const sizes = await Promise.all(assets.map(async (asset) => (await stat(asset)).size));
const largest = Math.max(0, ...sizes);
if (assets.length > 20_000 || largest > 25 * 1024 * 1024) {
  throw new Error(`Cloudflare Pages limits exceeded: ${assets.length} files, ${largest} bytes largest`);
}
console.log(`Built ${config.out}: ${assets.length} files, ${largest} bytes largest`);
