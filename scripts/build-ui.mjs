import { cp, mkdir, readdir, rm, stat } from "node:fs/promises";
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
await stat(path.join(config.modelCode, "manifest.v1.json"));
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
