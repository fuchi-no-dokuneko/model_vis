export class ModelStore {
  constructor(base = "model_code", fetcher = globalThis.fetch.bind(globalThis)) {
    this.base = base.replace(/\/$/, "");
    this.fetcher = fetcher;
    this.cache = new Map();
    this.manifest = null;
    this.index = [];
  }

  async get(relative) {
    const path = `${this.base}/${relative}`;
    if (!this.cache.has(path)) {
      const request = this.fetcher(path).then(async (response) => {
        if (!response.ok) throw new Error(`Unable to load ${relative}: ${response.status}`);
        return response.json();
      }).catch((error) => {
        this.cache.delete(path);
        throw error;
      });
      this.cache.set(path, request);
    }
    return this.cache.get(path);
  }

  async text(relative) {
    const path = `${this.base}/${relative}`;
    if (!this.cache.has(path)) {
      const request = this.fetcher(path).then(async (response) => {
        if (!response.ok) throw new Error(`Unable to load ${relative}: ${response.status}`);
        return response.text();
      }).catch((error) => {
        this.cache.delete(path);
        throw error;
      });
      this.cache.set(path, request);
    }
    return this.cache.get(path);
  }

  async initialize() {
    this.manifest = await this.get("manifest.v2.json");
    this.index = await this.get(this.manifest.search_index);
    return { manifest: this.manifest, index: this.index };
  }

  family(familyId) { return this.get(`families/${familyId}.json`); }
  version(versionId) { return this.get(`versions/${versionId}.json`); }
  graph(version) { return this.get(version.graph_ref); }
  blocks(version) { return this.get(version.blocks_ref); }
  trace(version) { return this.get(version.trace_ref); }
  config(version) { return this.get(version.config_ref); }
  traceConfig(version) { return version.trace_config_ref ? this.get(version.trace_config_ref) : this.config(version); }
  officialConfig(version) { return version.official_config_ref ? this.get(version.official_config_ref) : Promise.resolve(null); }
  configDiff(version) { return version.config_diff_ref ? this.get(version.config_diff_ref) : Promise.resolve(null); }
  source(sourceUid) { return this.get(`sources/${sourceUid}.json`); }
  sourceText(source) { return this.text(source.asset_path); }
  sharedBlock(block) { return this.get(block.pointer.target_asset); }
}

export function flattenConfig(value, prefix = "", output = new Map()) {
  if (value === null || typeof value !== "object") {
    output.set(prefix || "value", value);
    return output;
  }
  if (Array.isArray(value)) {
    output.set(prefix, JSON.stringify(value));
    return output;
  }
  for (const [key, child] of Object.entries(value)) {
    flattenConfig(child, prefix ? `${prefix}.${key}` : key, output);
  }
  return output;
}

export function configDifferences(left, right) {
  const a = flattenConfig(left);
  const b = flattenConfig(right);
  const keys = [...new Set([...a.keys(), ...b.keys()])].sort();
  return keys.filter((key) => JSON.stringify(a.get(key)) !== JSON.stringify(b.get(key))).map((key) => ({
    key,
    left: a.has(key) ? a.get(key) : "—",
    right: b.has(key) ? b.get(key) : "—",
  }));
}
