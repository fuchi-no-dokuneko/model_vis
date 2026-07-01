import { configDifferences, flattenConfig, ModelStore } from "./data-store.js";
import { graphBounds, layoutGraph, NODE_HEIGHT, NODE_WIDTH, projectGraph } from "./graph-model.js";

const $ = (selector) => document.querySelector(selector);
const store = new ModelStore();
const LIST_ROW_HEIGHT = 62;
const LAYER_COLORS = [
  "#08785d", "#356a9b", "#a76508", "#8a4f79", "#577b2f", "#a5483f",
  "#4f6f87", "#7a5d25", "#4b8079", "#76558c", "#87603f", "#3d737e",
];

const state = {
  manifest: null,
  index: [],
  filtered: [],
  mode: "family",
  current: null,
  family: null,
  graph: null,
  blocks: null,
  trace: null,
  config: null,
  scopeModuleId: null,
  hierarchyModuleId: null,
  inspected: null,
  selectedId: null,
  selectedCallId: null,
  selectedIds: new Set(),
  compareIds: [],
  graphView: { nodes: [], edges: [], layerGroups: [] },
  basePositions: new Map(),
  userPositions: new Map(),
  layoutKey: "",
  bounds: { width: 1200, height: 800 },
  zoom: 1,
  pan: { x: 24, y: 24 },
  pointers: new Map(),
  gesture: null,
  renderFrame: null,
  loadToken: 0,
  sourceToken: 0,
  sourceAssets: new Map(),
  currentSourceText: "",
  currentSourceRef: null,
  moduleExpanded: new Set(["module-00000"]),
  fileExpanded: new Set(),
  routeApplying: false,
};

function formatNumber(value) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(value || 0);
}

function shapeLabel(records = []) {
  return records.map((record) => record?.shape || record).filter(Array.isArray)
    .map((shape) => `[${shape.join(", ")}]`).join(" ");
}

function layerColor(layerGroupId) {
  if (!layerGroupId || !state.graph) return "#08785d";
  const group = state.graph.layer_groups.find((item) => item.layer_group_id === layerGroupId);
  return LAYER_COLORS[(group?.color_index || 0) % LAYER_COLORS.length];
}

function showStatus(message = "") {
  const status = $("#graph-status");
  status.hidden = !message;
  status.textContent = message;
}

function updateScrim() {
  const open = $("#sidebar").classList.contains("open")
    || $("#inspector").classList.contains("open")
    || !$("#compare-pane").hidden;
  $("#scrim").hidden = !open;
}

function openSidebar() { $("#sidebar").classList.add("open"); updateScrim(); }
function closeSidebar() { $("#sidebar").classList.remove("open"); updateScrim(); }
function openInspector() { $("#inspector").classList.add("open"); updateScrim(); }
function closeInspector() { $("#inspector").classList.remove("open"); updateScrim(); }

async function switchNavigator(panel) {
  document.querySelectorAll(".navigator-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.navigator === panel));
  document.querySelectorAll(".navigator-panel").forEach((section) => section.classList.toggle("active", section.id === `${panel}-navigator`));
  if (panel === "files") {
    await ensureSources();
    renderSourceTree();
  }
}

function populateCategories() {
  const categories = [...new Set(state.index.map((item) => item.category))].sort();
  for (const category of categories) {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category.replace(" models", "");
    $("#category").append(option);
  }
}

function filterIndex() {
  const query = $("#search").value.trim().toLowerCase();
  const category = $("#category").value;
  const sort = $("#sort").value;
  state.filtered = state.index.filter((item) => (
    (!category || item.category === category)
    && (!query || `${item.family_name} ${item.version_id} ${item.category} ${item.library}`.toLowerCase().includes(query))
  ));
  state.filtered.sort((left, right) => {
    if (sort === "parameters") return right.parameters - left.parameters || left.family_name.localeCompare(right.family_name);
    if (sort === "version") return left.version_id.localeCompare(right.version_id);
    if (sort === "sources") return right.source_count - left.source_count || left.family_name.localeCompare(right.family_name);
    return left.family_name.localeCompare(right.family_name) || left.version_id.localeCompare(right.version_id);
  });
  $("#model-list-inner").style.height = `${state.filtered.length * LIST_ROW_HEIGHT}px`;
  $("#result-count").textContent = `${state.filtered.length} model${state.filtered.length === 1 ? "" : "s"}`;
  renderListWindow();
}

function renderListWindow() {
  const viewport = $("#model-list");
  const visibleHeight = viewport.clientHeight || 600;
  const start = Math.max(0, Math.floor(viewport.scrollTop / LIST_ROW_HEIGHT) - 3);
  const end = Math.min(state.filtered.length, Math.ceil((viewport.scrollTop + visibleHeight) / LIST_ROW_HEIGHT) + 3);
  const fragment = document.createDocumentFragment();
  for (let index = start; index < end; index += 1) {
    const item = state.filtered[index];
    const row = document.createElement("div");
    row.className = `model-item${state.current?.version_id === item.version_id ? " active" : ""}`;
    row.style.top = `${index * LIST_ROW_HEIGHT}px`;
    const open = document.createElement("button");
    open.className = "model-open";
    open.setAttribute("role", "option");
    open.setAttribute("aria-selected", String(state.current?.version_id === item.version_id));
    const name = document.createElement("span");
    name.className = "model-name";
    name.textContent = item.family_name;
    const meta = document.createElement("span");
    meta.className = "model-meta";
    for (const text of [item.category.replace(" models", ""), item.version_id, `${formatNumber(item.parameters)} params`]) {
      const value = document.createElement("span");
      value.textContent = text;
      meta.append(value);
    }
    open.append(name, meta);
    open.addEventListener("click", async () => {
      await loadVersion(item.version_id);
      await setMode("module");
      switchNavigator("modules");
    });
    const label = document.createElement("label");
    label.className = "compare-check";
    label.title = "Select for comparison";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.compareIds.includes(item.version_id);
    checkbox.setAttribute("aria-label", `Compare ${item.family_name}`);
    checkbox.addEventListener("change", () => toggleCompareVersion(item.version_id, checkbox.checked));
    label.append(checkbox);
    row.append(open, label);
    fragment.append(row);
  }
  $("#model-list-inner").replaceChildren(fragment);
}

function toggleCompareVersion(versionId, selected) {
  state.compareIds = state.compareIds.filter((id) => id !== versionId);
  if (selected) {
    state.compareIds.push(versionId);
    if (state.compareIds.length > 2) state.compareIds.shift();
  }
  $("#compare-count").textContent = state.compareIds.length;
  $("#compare-count").hidden = state.compareIds.length === 0;
  renderListWindow();
}

function moduleById(moduleId) {
  return state.graph?.modules.find((module) => module.module_id === moduleId) || null;
}

function moduleByPath(path) {
  return state.graph?.modules.find((module) => module.qualified_name === path) || null;
}

function expandModuleAncestors(module) {
  let current = module;
  while (current) {
    state.moduleExpanded.add(current.module_id);
    current = moduleById(current.parent_module_id);
  }
}

function sourceRefFor(value) {
  return value?.source_ref || value?.source_refs?.[0] || null;
}

function routePath() {
  if (!state.current) return "#/";
  const segments = ["", "version", encodeURIComponent(state.current.version_id), "view", state.mode];
  const scope = moduleById(state.scopeModuleId);
  if (scope && scope.qualified_name !== "<root>") segments.push("module", encodeURIComponent(scope.qualified_name));
  if (state.selectedCallId) segments.push("call", encodeURIComponent(state.selectedCallId));
  if (state.selectedId) segments.push("operation", encodeURIComponent(state.selectedId));
  if (state.currentSourceRef?.source_uid) {
    segments.push("source", encodeURIComponent(state.currentSourceRef.source_uid));
    if (state.currentSourceRef.executed_line) segments.push("line", String(state.currentSourceRef.executed_line));
  }
  return `#${segments.join("/")}`;
}

function syncRoute({ push = true } = {}) {
  if (state.routeApplying || !state.current) return;
  const hash = routePath();
  const browserUrl = `${location.pathname}${location.search}${hash}`;
  if (push) history.pushState(null, "", browserUrl);
  else history.replaceState(null, "", browserUrl);
  $("#uri-input").value = `modelvis:${hash.slice(1)}`;
}

function parseRoute(value) {
  let route = value.trim();
  if (route.startsWith("modelvis:")) route = route.slice("modelvis:".length);
  else if (route.includes("#")) route = route.slice(route.indexOf("#") + 1);
  route = route.replace(/^#/, "");
  const parts = route.split("/").filter(Boolean).map(decodeURIComponent);
  const result = {};
  for (let index = 0; index < parts.length; index += 2) result[parts[index]] = parts[index + 1];
  return result;
}

async function applyRoute(value) {
  const route = parseRoute(value);
  if (!route.version) throw new Error("URI must include /version/<version-id>");
  if (!state.index.some((item) => item.version_id === route.version)) throw new Error(`Unknown model version: ${route.version}`);
  if (route.view && !["family", "module", "operation"].includes(route.view)) {
    throw new Error(`Unknown graph detail mode: ${route.view}`);
  }
  state.routeApplying = true;
  try {
    await loadVersion(route.version, { sync: false });
    const mode = ["family", "module", "operation"].includes(route.view) ? route.view : "module";
    await setMode(mode, { sync: false });
    if (route.module && state.graph) {
      const module = moduleByPath(route.module);
      if (!module) throw new Error(`Unknown module path: ${route.module}`);
      state.scopeModuleId = module.module_id;
      state.hierarchyModuleId = module.module_id;
      expandModuleAncestors(module);
    }
    if (route.call) {
      const call = state.graph?.module_calls.find((item) => item.call_id === route.call);
      if (!call) throw new Error(`Unknown runtime call: ${route.call}`);
      state.selectedCallId = call.call_id;
      state.hierarchyModuleId = call.module_id;
      expandModuleAncestors(moduleById(call.module_id));
    }
    await renderMode({ fit: true });
    if (route.operation) {
      const item = state.graphView.nodes.find((node) => node.id === route.operation);
      if (!item) throw new Error(`Unknown operation in current scope: ${route.operation}`);
      selectNode(item, {}, { sync: false });
    } else if (route.call) {
      const call = state.graph.module_calls.find((item) => item.call_id === route.call);
      const item = state.graphView.nodes.find((node) => call.operation_ids.includes(node.id));
      if (item) selectNode(item, {}, { sync: false });
      else renderInspector(call);
    }
    if (route.source) {
      const source = await ensureSourceAsset(route.source);
      if (!source) throw new Error(`Unknown source asset: ${route.source}`);
      const line = Number(route.line || 1);
      if (!Number.isInteger(line) || line < 1 || line > source.line_count) {
        throw new Error(`Invalid source line: ${route.line}`);
      }
      await switchInspectorPanel("source");
      await renderSource({
        source_ref: {
          source_uid: route.source,
          file: source.relative_file,
          start_line: line,
          end_line: line,
          executed_line: line,
          symbol: source.relative_file,
        },
      });
    }
    renderModuleTree();
  } finally {
    state.routeApplying = false;
    syncRoute({ push: false });
  }
}

function positionStorageKey() {
  return `model-vis-layout:${state.current?.structure_key || "none"}:${state.mode}:${state.scopeModuleId || "root"}`;
}

function loadUserPositions() {
  try {
    state.userPositions = new Map(JSON.parse(localStorage.getItem(positionStorageKey()) || "[]"));
  } catch {
    state.userPositions = new Map();
  }
}

function saveUserPositions() {
  localStorage.setItem(positionStorageKey(), JSON.stringify([...state.userPositions]));
}

function positionFor(id) {
  return state.userPositions.get(id) || state.basePositions.get(id) || { x: 40, y: 40 };
}

function allPositions() {
  return new Map(state.graphView.nodes.map((node) => [node.id, positionFor(node.id)]));
}

function renderBreadcrumbs() {
  const nav = $("#breadcrumbs");
  nav.replaceChildren();
  if (!state.current) return;
  const crumbs = [
    { label: state.current.category.replace(" models", ""), action: () => setMode("family") },
    { label: state.current.family_name, action: () => setMode("family") },
    { label: state.current.version_id, action: () => selectModule("module-00000") },
  ];
  const scope = moduleById(state.scopeModuleId);
  if (scope && scope.qualified_name !== "<root>") {
    const parts = scope.qualified_name.split(".");
    for (let index = 0; index < parts.length; index += 1) {
      const path = parts.slice(0, index + 1).join(".");
      const module = moduleByPath(path);
      if (module) crumbs.push({ label: parts[index], action: () => selectModule(module.module_id) });
    }
  }
  if (state.mode === "operation") crumbs.push({ label: "Operations", action: () => setMode("operation") });
  crumbs.forEach((crumb, index) => {
    const button = document.createElement("button");
    button.className = `breadcrumb${index === crumbs.length - 1 ? " current" : ""}`;
    button.textContent = crumb.label;
    button.addEventListener("click", crumb.action);
    nav.append(button);
  });
}

async function ensureGraphAssets() {
  if (!state.current) return;
  const [graph, trace] = await Promise.all([
    state.graph ? Promise.resolve(state.graph) : store.graph(state.current),
    state.trace ? Promise.resolve(state.trace) : store.trace(state.current),
  ]);
  state.graph = graph;
  state.trace = trace;
  state.scopeModuleId ||= graph.modules[0]?.module_id || null;
  renderModuleTree();
}

async function ensureModeAssets() {
  if (!state.current) return;
  if (state.mode === "family") {
    state.family ||= await store.family(state.current.family_id);
    return;
  }
  await ensureGraphAssets();
}

async function loadVersion(versionId, { sync = true } = {}) {
  const token = ++state.loadToken;
  showStatus("Loading model metadata...");
  const [version, family] = await Promise.all([store.version(versionId), store.family((state.index.find((item) => item.version_id === versionId) || {}).family_id || versionId)]).catch(async () => {
    const versionValue = await store.version(versionId);
    return [versionValue, await store.family(versionValue.family_id)];
  });
  if (token !== state.loadToken) return;
  state.current = version;
  state.family = family;
  state.graph = null;
  state.blocks = null;
  state.trace = null;
  state.config = null;
  state.scopeModuleId = null;
  state.hierarchyModuleId = null;
  state.selectedId = null;
  state.selectedCallId = null;
  state.selectedIds.clear();
  state.inspected = version;
  state.sourceAssets = new Map();
  state.currentSourceText = "";
  state.currentSourceRef = null;
  state.moduleExpanded = new Set(["module-00000"]);
  state.pan = { x: 24, y: 24 };
  state.zoom = 1;
  renderListWindow();
  renderInspector(version);
  await renderMode({ fit: true });
  closeSidebar();
  if (sync) syncRoute();
}

async function setMode(mode, { sync = true } = {}) {
  state.mode = mode;
  state.selectedId = null;
  state.selectedCallId = null;
  state.selectedIds.clear();
  document.querySelectorAll(".mode").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  updateDensityButton();
  await renderMode({ fit: true });
  if (sync) syncRoute();
}

async function selectModule(moduleId, { sync = true } = {}) {
  if (!state.graph) await ensureGraphAssets();
  const module = moduleById(moduleId);
  if (!module) return;
  state.scopeModuleId = moduleId;
  state.hierarchyModuleId = moduleId;
  state.selectedCallId = null;
  expandModuleAncestors(module);
  if (state.mode === "family") state.mode = "module";
  document.querySelectorAll(".mode").forEach((button) => button.classList.toggle("active", button.dataset.mode === state.mode));
  renderModuleTree();
  renderInspector(module);
  await renderMode({ fit: true });
  if (sync) syncRoute();
}

async function renderMode({ fit = false } = {}) {
  if (!state.current) return;
  showStatus("Loading view...");
  try {
    await ensureModeAssets();
    state.graphView = projectGraph({
      mode: state.mode,
      current: state.current,
      family: state.family,
      index: state.index,
      graph: state.graph,
      scopeModuleId: state.scopeModuleId,
    });
    const nextLayoutKey = positionStorageKey();
    state.basePositions = layoutGraph(state.graphView.nodes, state.graphView.edges);
    if (state.layoutKey !== nextLayoutKey) {
      state.layoutKey = nextLayoutKey;
      loadUserPositions();
    }
    state.bounds = graphBounds(state.graphView.nodes, allPositions());
    $("#graph-canvas").style.width = `${state.bounds.width}px`;
    $("#graph-canvas").style.height = `${state.bounds.height}px`;
    $("#edges").setAttribute("viewBox", `0 0 ${state.bounds.width} ${state.bounds.height}`);
    $("#empty-state").hidden = state.graphView.nodes.length > 0;
    renderBreadcrumbs();
    updateTransform();
    renderVisibleGraph();
    if (fit) requestAnimationFrame(fitGraph);
  } catch (error) {
    $("#empty-state").hidden = false;
    $("#empty-state").textContent = error.message;
  } finally {
    showStatus("");
  }
}

function renderModuleTree() {
  const container = $("#module-tree");
  container.replaceChildren();
  if (!state.graph?.modules) return;
  const query = $("#module-search").value.trim().toLowerCase();
  const byId = new Map(state.graph.modules.map((module) => [module.module_id, module]));
  const visibleMatches = new Set();
  if (query) {
    for (const module of state.graph.modules) {
      if (`${module.qualified_name} ${module.class_name}`.toLowerCase().includes(query)) {
        let current = module;
        while (current) {
          visibleMatches.add(current.module_id);
          current = byId.get(current.parent_module_id);
        }
      }
    }
  }
  const fragment = document.createDocumentFragment();
  const visit = (module, depth) => {
    if (query && !visibleMatches.has(module.module_id)) return;
    const row = document.createElement("button");
    row.className = `tree-row${(state.hierarchyModuleId || state.scopeModuleId) === module.module_id ? " active" : ""}`;
    row.dataset.moduleId = module.module_id;
    row.dataset.modulePath = module.qualified_name;
    row.style.setProperty("--depth", depth);
    row.style.setProperty("--tree-color", layerColor(module.layer_group_id));
    row.setAttribute("role", "treeitem");
    row.setAttribute("aria-level", depth + 1);
    row.setAttribute("aria-expanded", module.child_module_ids.length ? String(state.moduleExpanded.has(module.module_id) || Boolean(query)) : "false");
    const disclosure = document.createElement("span");
    disclosure.className = "tree-disclosure";
    disclosure.textContent = module.child_module_ids.length ? ((state.moduleExpanded.has(module.module_id) || query) ? "▾" : "▸") : "";
    const label = document.createElement("span");
    label.className = "tree-label";
    label.textContent = module.qualified_name === "<root>" ? state.current.family_name : module.qualified_name.split(".").at(-1);
    const className = document.createElement("span");
    className.className = "tree-class";
    className.textContent = module.display_name;
    label.append(className);
    row.append(disclosure, label);
    row.addEventListener("click", async (event) => {
      if (event.target.closest(".tree-disclosure") && module.child_module_ids.length) {
        if (state.moduleExpanded.has(module.module_id)) state.moduleExpanded.delete(module.module_id);
        else state.moduleExpanded.add(module.module_id);
        renderModuleTree();
        return;
      }
      await selectModule(module.module_id);
    });
    fragment.append(row);
    if (state.moduleExpanded.has(module.module_id) || query) {
      if (module.call_ids.length > 1) {
        module.call_ids.forEach((callId, callIndex) => {
          const call = state.graph.module_calls.find((item) => item.call_id === callId);
          if (!call) return;
          const callRow = document.createElement("button");
          callRow.className = `tree-row${state.selectedId === call.operation_ids[0] ? " active" : ""}`;
          callRow.dataset.callId = callId;
          callRow.style.setProperty("--depth", depth + 1);
          callRow.style.setProperty("--tree-color", layerColor(module.layer_group_id));
          callRow.setAttribute("role", "treeitem");
          callRow.setAttribute("aria-level", depth + 2);
          const callIcon = document.createElement("span");
          callIcon.className = "tree-disclosure";
          callIcon.textContent = "↳";
          const callLabel = document.createElement("span");
          callLabel.className = "tree-label";
          callLabel.textContent = `call ${callIndex + 1}`;
          const callShape = document.createElement("span");
          callShape.className = "tree-class";
          callShape.textContent = `${shapeLabel(call.input_ports)} → ${shapeLabel(call.output_ports)}`;
          callLabel.append(callShape);
          callRow.append(callIcon, callLabel);
          callRow.addEventListener("click", async () => {
            state.scopeModuleId = module.module_id;
            if (state.mode !== "operation") await setMode("operation", { sync: false });
            state.selectedCallId = callId;
            const item = state.graphView.nodes.find((node) => call.operation_ids.includes(node.id));
            if (item) selectNode(item);
            else {
              renderInspector(call);
              syncRoute();
            }
          });
          fragment.append(callRow);
        });
      }
      const children = module.child_module_ids.map((id) => byId.get(id)).filter(Boolean)
        .sort((left, right) => left.qualified_name.localeCompare(right.qualified_name, undefined, { numeric: true }));
      children.forEach((child) => visit(child, depth + 1));
    }
  };
  visit(state.graph.modules[0], 0);
  container.append(fragment);
  const rows = [...container.querySelectorAll(".tree-row")];
  const active = rows.find((row) => row.classList.contains("active")) || rows[0];
  rows.forEach((row) => { row.tabIndex = row === active ? 0 : -1; });
}

function focusModuleTreeRow(row) {
  if (!row) return;
  $("#module-tree").querySelectorAll(".tree-row").forEach((item) => { item.tabIndex = -1; });
  row.tabIndex = 0;
  row.focus();
}

function focusRenderedModule(modulePath) {
  requestAnimationFrame(() => focusModuleTreeRow(
    [...$("#module-tree").querySelectorAll(".tree-row")]
      .find((item) => item.dataset.modulePath === modulePath),
  ));
}

function handleModuleTreeKeydown(event) {
  const row = event.target.closest(".tree-row");
  if (!row) return;
  const rows = [...$("#module-tree").querySelectorAll(".tree-row")];
  const index = rows.indexOf(row);
  const level = Number(row.getAttribute("aria-level") || 1);
  if (["ArrowDown", "ArrowUp", "Home", "End", "ArrowRight", "ArrowLeft", "Enter", " "].includes(event.key)) {
    event.preventDefault();
  }
  if (event.key === "ArrowDown") focusModuleTreeRow(rows[Math.min(rows.length - 1, index + 1)]);
  else if (event.key === "ArrowUp") focusModuleTreeRow(rows[Math.max(0, index - 1)]);
  else if (event.key === "Home") focusModuleTreeRow(rows[0]);
  else if (event.key === "End") focusModuleTreeRow(rows.at(-1));
  else if (event.key === "Enter" || event.key === " ") row.click();
  else if (event.key === "ArrowRight") {
    if (row.dataset.moduleId && row.getAttribute("aria-expanded") === "false") {
      state.moduleExpanded.add(row.dataset.moduleId);
      const path = row.dataset.modulePath;
      renderModuleTree();
      focusRenderedModule(path);
    } else if (rows[index + 1] && Number(rows[index + 1].getAttribute("aria-level")) > level) {
      focusModuleTreeRow(rows[index + 1]);
    }
  } else if (event.key === "ArrowLeft") {
    if (row.dataset.moduleId && row.getAttribute("aria-expanded") === "true") {
      state.moduleExpanded.delete(row.dataset.moduleId);
      const path = row.dataset.modulePath;
      renderModuleTree();
      focusRenderedModule(path);
    } else {
      for (let previous = index - 1; previous >= 0; previous -= 1) {
        if (Number(rows[previous].getAttribute("aria-level")) < level) {
          focusModuleTreeRow(rows[previous]);
          break;
        }
      }
    }
  }
}

async function ensureSourceAsset(sourceUid) {
  if (state.sourceAssets.has(sourceUid)) return state.sourceAssets.get(sourceUid);
  try {
    const source = await store.source(sourceUid);
    state.sourceAssets.set(sourceUid, source);
    return source;
  } catch {
    return null;
  }
}

async function ensureSources() {
  if (!state.current?.sources) return [];
  const values = await Promise.all(state.current.sources.map(ensureSourceAsset));
  return values.filter(Boolean);
}

async function renderSourceTree() {
  const container = $("#source-tree");
  container.replaceChildren();
  const sources = [...state.sourceAssets.values()].sort((left, right) => left.relative_file.localeCompare(right.relative_file));
  const root = { children: new Map() };
  for (const source of sources) {
    let current = root;
    const parts = source.relative_file.split("/");
    parts.forEach((name, index) => {
      if (!current.children.has(name)) {
        current.children.set(name, {
          name,
          path: parts.slice(0, index + 1).join("/"),
          children: new Map(),
          source: null,
        });
      }
      current = current.children.get(name);
    });
    current.source = source;
  }
  const fragment = document.createDocumentFragment();
  const renderEntry = (entry, depth) => {
    const folder = entry.children.size > 0 && !entry.source;
    if (depth === 0 && !state.fileExpanded.size) state.fileExpanded.add(entry.path);
    const expanded = state.fileExpanded.has(entry.path);
    const row = document.createElement("button");
    row.className = `tree-row${state.currentSourceRef?.source_uid === entry.source?.source_uid ? " active" : ""}`;
    row.style.setProperty("--depth", depth);
    const icon = document.createElement("span");
    icon.className = "tree-disclosure";
    icon.textContent = folder ? (expanded ? "▾" : "▸") : "·";
    const label = document.createElement("span");
    label.className = "tree-label";
    label.textContent = entry.name;
    row.append(icon, label);
    row.addEventListener("click", async () => {
      if (folder) {
        if (expanded) state.fileExpanded.delete(entry.path);
        else state.fileExpanded.add(entry.path);
        renderSourceTree();
        return;
      }
      const source = entry.source;
      if (!source) return;
      await switchInspectorPanel("source");
      await renderSource({ source_ref: {
        source_uid: source.source_uid,
        file: source.relative_file,
        symbol: source.relative_file,
        start_line: 1,
        end_line: source.line_count,
        executed_line: 1,
      } });
      if (window.innerWidth <= 980) openInspector();
    });
    fragment.append(row);
    if (folder && expanded) {
      [...entry.children.values()]
        .sort((left, right) => left.name.localeCompare(right.name))
        .forEach((child) => renderEntry(child, depth + 1));
    }
  };
  [...root.children.values()]
    .sort((left, right) => left.name.localeCompare(right.name))
    .forEach((entry) => renderEntry(entry, 0));
  container.append(fragment);
}

function visibleNodeIds() {
  const viewport = $("#graph-viewport");
  const width = viewport.clientWidth || 900;
  const height = viewport.clientHeight || 650;
  const margin = 320;
  const left = (-state.pan.x) / state.zoom - margin;
  const top = (-state.pan.y) / state.zoom - margin;
  const right = left + width / state.zoom + margin * 2;
  const bottom = top + height / state.zoom + margin * 2;
  return new Set(state.graphView.nodes.filter((node) => {
    const position = positionFor(node.id);
    return position.x + NODE_WIDTH >= left && position.x <= right
      && position.y + NODE_HEIGHT >= top && position.y <= bottom;
  }).map((node) => node.id));
}

function scheduleVisibleRender() {
  if (state.renderFrame !== null) return;
  state.renderFrame = requestAnimationFrame(() => {
    state.renderFrame = null;
    renderVisibleGraph();
  });
}

function portBand(ports, direction) {
  const band = document.createElement("div");
  band.className = `node-ports ${direction === "input" ? "inputs" : "outputs"}`;
  if (!ports.length) {
    const empty = document.createElement("span");
    empty.className = "node-port";
    band.append(empty);
    return band;
  }
  for (const port of ports) {
    const item = document.createElement("div");
    item.className = "node-port";
    item.dataset.portId = port.port_id;
    item.title = [
      port.name || direction,
      shapeLabel([port]),
      port.dtype,
      port.device,
      port.required ? "required" : "optional",
      port.alias_kind,
    ].filter(Boolean).join(" · ");
    const name = document.createElement("span");
    name.className = "port-name";
    name.textContent = port.name || `${direction} ${port.index}`;
    const shape = document.createElement("span");
    shape.className = "port-shape";
    shape.textContent = shapeLabel([port]) || "non-tensor";
    item.append(name, shape);
    band.append(item);
  }
  return band;
}

function renderVisibleGraph() {
  const visible = visibleNodeIds();
  if (state.selectedId) visible.add(state.selectedId);
  const fragment = document.createDocumentFragment();
  for (const item of state.graphView.nodes) {
    if (!visible.has(item.id)) continue;
    const position = positionFor(item.id);
    const node = document.createElement("article");
    node.className = "graph-node";
    node.dataset.id = item.id;
    node.dataset.kind = item.kind;
    node.classList.toggle("selected", state.selectedId === item.id);
    node.classList.toggle("multi-selected", state.selectedIds.has(item.id));
    node.style.left = `${position.x}px`;
    node.style.top = `${position.y}px`;
    node.style.setProperty("--layer-color", layerColor(item.layerGroupId));
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `${item.title}, ${item.inputPorts.length} inputs, ${item.outputPorts.length} outputs`);
    const core = document.createElement("div");
    core.className = "node-core";
    const title = document.createElement("div");
    title.className = "node-title";
    title.textContent = item.title;
    const subtitle = document.createElement("div");
    subtitle.className = "node-shape";
    subtitle.textContent = item.subtitle || item.kind;
    core.append(title, subtitle);
    if (item.layerGroupId) {
      const layer = state.graph?.layer_groups.find((group) => group.layer_group_id === item.layerGroupId);
      const badge = document.createElement("div");
      badge.className = "node-layer";
      badge.textContent = layer?.qualified_name || item.layerGroupId;
      core.append(badge);
    }
    node.append(portBand(item.inputPorts, "input"), core, portBand(item.outputPorts, "output"));
    node.addEventListener("pointerdown", startNodeDrag);
    node.addEventListener("click", (event) => selectNode(item, event));
    node.addEventListener("dblclick", (event) => drillIntoNode(item, event));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter") drillIntoNode(item, event);
      if (event.key === " ") { event.preventDefault(); selectNode(item, event); }
    });
    fragment.append(node);
  }
  $("#nodes").replaceChildren(fragment);
  renderEdges(visible);
  renderLayerGroups();
  renderMinimap();
  const virtualized = visible.size < state.graphView.nodes.length;
  showStatus(virtualized ? `${visible.size} / ${state.graphView.nodes.length} nodes visible` : "");
}

function portPoint(node, portId, direction) {
  const ports = direction === "output" ? node.outputPorts : node.inputPorts;
  const index = Math.max(0, ports.findIndex((port) => port.port_id === portId));
  const count = Math.max(1, ports.length);
  const position = positionFor(node.id);
  return {
    x: position.x + NODE_WIDTH * ((index + 0.5) / count),
    y: position.y + (direction === "output" ? NODE_HEIGHT : 0),
  };
}

function renderEdges(visible) {
  const byId = new Map(state.graphView.nodes.map((node) => [node.id, node]));
  const svg = $("#edges");
  const fragment = document.createDocumentFragment();
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
  marker.setAttribute("id", "edge-arrow");
  marker.setAttribute("viewBox", "0 0 10 10");
  marker.setAttribute("refX", "9");
  marker.setAttribute("refY", "5");
  marker.setAttribute("markerWidth", "5");
  marker.setAttribute("markerHeight", "5");
  marker.setAttribute("orient", "auto-start-reverse");
  const arrow = document.createElementNS("http://www.w3.org/2000/svg", "path");
  arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
  arrow.setAttribute("fill", "#87918a");
  marker.append(arrow);
  defs.append(marker);
  fragment.append(defs);
  for (const edge of state.graphView.edges) {
    if (!visible.has(edge.source) || !visible.has(edge.target)) continue;
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) continue;
    const before = portPoint(source, edge.source_port, "output");
    const after = portPoint(target, edge.target_port, "input");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const bend = Math.max(34, Math.abs(after.y - before.y) / 2);
    path.setAttribute("d", `M ${before.x} ${before.y} C ${before.x} ${before.y + bend}, ${after.x} ${after.y - bend}, ${after.x} ${after.y}`);
    path.dataset.confidence = edge.confidence || "exact";
    path.classList.toggle("active", edge.source === state.selectedId || edge.target === state.selectedId);
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${edge.tensor_id || "route"} ${shapeLabel([{ shape: edge.shape }])} ${edge.confidence || "exact"}`;
    path.append(title);
    fragment.append(path);
  }
  svg.replaceChildren(fragment);
}

function renderLayerGroups() {
  const container = $("#layer-groups");
  const fragment = document.createDocumentFragment();
  for (const group of state.graphView.layerGroups || []) {
    const nodes = state.graphView.nodes.filter((node) => node.layerGroupId === group.layer_group_id);
    if (!nodes.length) continue;
    const positions = nodes.map((node) => positionFor(node.id));
    const left = Math.min(...positions.map((position) => position.x)) - 18;
    const top = Math.min(...positions.map((position) => position.y)) - 26;
    const right = Math.max(...positions.map((position) => position.x + NODE_WIDTH)) + 18;
    const bottom = Math.max(...positions.map((position) => position.y + NODE_HEIGHT)) + 18;
    const boundary = document.createElement("div");
    boundary.className = "layer-boundary";
    boundary.style.left = `${left}px`;
    boundary.style.top = `${top}px`;
    boundary.style.width = `${right - left}px`;
    boundary.style.height = `${bottom - top}px`;
    boundary.style.setProperty("--layer-color", layerColor(group.layer_group_id));
    const label = document.createElement("div");
    label.className = "layer-boundary-label";
    label.textContent = group.qualified_name;
    boundary.append(label);
    fragment.append(boundary);
  }
  container.replaceChildren(fragment);
}

function renderMinimap() {
  const canvas = $("#minimap");
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  const scale = Math.min(canvas.width / state.bounds.width, canvas.height / state.bounds.height);
  for (const node of state.graphView.nodes) {
    context.fillStyle = layerColor(node.layerGroupId);
    const position = positionFor(node.id);
    context.fillRect(position.x * scale, position.y * scale, Math.max(3, NODE_WIDTH * scale), Math.max(2, 7 * scale));
  }
  const viewport = $("#graph-viewport");
  context.strokeStyle = "#08785d";
  context.lineWidth = 3;
  context.strokeRect(
    Math.max(0, -state.pan.x / state.zoom) * scale,
    Math.max(0, -state.pan.y / state.zoom) * scale,
    Math.min(state.bounds.width, viewport.clientWidth / state.zoom) * scale,
    Math.min(state.bounds.height, viewport.clientHeight / state.zoom) * scale,
  );
}

function selectNode(item, event = {}, { sync = true } = {}) {
  event.stopPropagation?.();
  if (event.ctrlKey || event.metaKey) {
    if (state.selectedIds.has(item.id)) state.selectedIds.delete(item.id);
    else state.selectedIds.add(item.id);
  } else {
    state.selectedIds.clear();
    state.selectedIds.add(item.id);
  }
  state.selectedId = item.id;
  state.selectedCallId = item.raw.call_id || null;
  if (item.raw.module_id) {
    state.hierarchyModuleId = item.raw.module_id;
    expandModuleAncestors(moduleById(item.raw.module_id));
    renderModuleTree();
    requestAnimationFrame(() => {
      const row = $("#module-tree").querySelector(`[data-module-id="${item.raw.module_id}"]`);
      row?.scrollIntoView({ block: "nearest" });
    });
  }
  state.inspected = item.raw;
  renderInspector(item.raw);
  renderVisibleGraph();
  if (sync) syncRoute();
  if (window.innerWidth <= 980) openInspector();
}

async function drillIntoNode(item, event = {}) {
  event.stopPropagation?.();
  if (state.mode === "family") {
    const versionId = item.id.startsWith("version:") ? item.id.slice(8) : state.current.version_id;
    await loadVersion(versionId);
    await setMode("module");
    switchNavigator("modules");
    return;
  }
  const moduleId = item.raw.module_id;
  if (moduleId) {
    await selectModule(moduleId);
    switchNavigator("modules");
  } else if (state.mode === "module") {
    await setMode("operation");
  }
}

function metadataRows(value) {
  const preferred = [
    "status", "library", "architecture_key", "entrypoint_class", "execution_mode", "kind", "name",
    "qualified_name", "module_path", "class_name", "block_type", "trace_confidence", "operation_count", "block_count",
  ];
  const rows = [];
  for (const key of preferred) if (value?.[key] !== undefined && value[key] !== null) rows.push([key.replaceAll("_", " "), value[key]]);
  if (value?.parameters !== undefined) {
    const count = typeof value.parameters === "number" ? value.parameters : value.parameters.total;
    if (Number.isFinite(count)) rows.push(["parameters", count.toLocaleString()]);
  }
  if (value?.input_ports) rows.push(["inputs", value.input_ports.length]);
  if (value?.output_ports) rows.push(["outputs", value.output_ports.length]);
  if (value?.layer_group_id) rows.push(["layer group", value.layer_group_id]);
  if (value?.sources) rows.push(["source assets", value.sources.length]);
  return rows;
}

function renderInspector(value) {
  value ||= state.current || {};
  state.inspected = value;
  $("#inspector-title").textContent = value.display_name || value.qualified_name || value.name || value.family_name || "Inspector";
  const list = document.createElement("dl");
  for (const [name, content] of metadataRows(value)) {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = name;
    detail.textContent = String(content);
    list.append(term, detail);
  }
  $("#metadata").replaceChildren(list);
  renderShapes(value);
  renderRuntime(value);
  const ref = sourceRefFor(value);
  $("#source-reference").textContent = ref?.file
    ? `${ref.file}:${ref.executed_line || ref.start_line} · ${ref.symbol || value.target || "source"}`
    : "Select a module, operation, or source file";
  if ($("#source-panel").classList.contains("active")) renderSource(value);
  else state.currentSourceRef = null;
}

function normalizeShapeRecords(value) {
  const records = [];
  for (const [role, items] of [
    ["input", value?.input_ports || value?.inputs || value?.input_shapes || []],
    ["output", value?.output_ports || value?.outputs || value?.output_shapes || value?.top_level_outputs || []],
  ]) {
    for (const item of items) {
      if (Array.isArray(item)) records.push({ role, shape: item });
      else if (item?.shape) records.push({ role: item.role || role, ...item });
    }
  }
  return records;
}

function renderShapes(value) {
  const fragment = document.createDocumentFragment();
  const records = normalizeShapeRecords(value);
  if (!records.length) {
    const empty = document.createElement("div");
    empty.className = "config-view";
    empty.textContent = "No observed tensor ports are attached to this selection.";
    fragment.append(empty);
  }
  for (const record of records) {
    const row = document.createElement("div");
    row.className = "shape-record";
    const role = document.createElement("div");
    role.className = "shape-role";
    role.textContent = `${record.role} · ${record.name || record.container_path || record.index || 0}`;
    const shape = document.createElement("div");
    shape.className = "shape-value";
    shape.textContent = `[${record.shape.join(", ")}]`;
    const meta = document.createElement("div");
    meta.className = "shape-meta";
    const binding = record.supplied_by === "positional" && record.position !== null
      ? `position ${record.position}`
      : (record.keyword_name ? `keyword ${record.keyword_name}` : record.supplied_by);
    const mutation = record.mutation_version_before !== record.mutation_version_after
      ? `mutation ${record.mutation_version_before ?? "n/a"}→${record.mutation_version_after ?? "n/a"}`
      : (record.mutation_version !== undefined ? `version ${record.mutation_version ?? "n/a"}` : null);
    meta.textContent = [
      record.tensor_id,
      record.dtype,
      record.device,
      record.required ? "required" : "optional",
      record.argument_kind,
      binding,
      record.alias_kind,
      mutation,
    ].filter(Boolean).join(" · ");
    row.append(role, shape, meta);
    fragment.append(row);
  }
  $("#shape-list").replaceChildren(fragment);
}

function appendRuntimeSection(container, titleText, rows) {
  if (!rows?.length) return;
  const section = document.createElement("section");
  section.className = "runtime-section";
  const title = document.createElement("h3");
  title.textContent = titleText;
  section.append(title);
  for (const [key, value] of rows) {
    const row = document.createElement("div");
    row.className = "runtime-row";
    const name = document.createElement("div");
    name.className = "runtime-key";
    name.textContent = key;
    const content = document.createElement("div");
    content.className = "runtime-value";
    content.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    row.append(name, content);
    section.append(row);
  }
  container.append(section);
}

function renderRuntime(value) {
  const container = $("#runtime-view");
  container.replaceChildren();
  const module = value?.module_id ? moduleById(value.module_id) : (value?.qualified_name ? moduleByPath(value.qualified_name) : null);
  const constructor = value?.constructor || module?.constructor;
  appendRuntimeSection(container, "Constructor", (constructor?.effective_arguments || []).map((item) => [
    [item.name, item.supplied_by, item.origin, item.config_path].filter(Boolean).join(" · "), item.value,
  ]));
  appendRuntimeSection(container, "Runtime call", (value?.call_arguments || []).map((item) => [item.name, item.value]));
  const call = state.graph?.module_calls.find((item) => item.call_id === value?.call_id);
  appendRuntimeSection(container, "Module call", (call?.call_arguments || []).map((item) => [item.name, item.value]));
  const tensorParameters = Array.isArray(value?.parameters) ? value.parameters : (module?.parameters || []);
  appendRuntimeSection(container, "Tensor parameters", tensorParameters.map((item) => [
    item.name, `${shapeLabel([item])} · ${item.dtype} · ${item.trainable ? "trainable" : "fixed"}`,
  ]));
  if (!container.children.length) container.textContent = "No constructor or runtime argument record is attached to this selection.";
}

function appendHighlightedCode(container, text) {
  const pattern = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|#.*|\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|raise|return|True|try|while|with|yield)\b|\b\d+(?:\.\d+)?\b)/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    container.append(document.createTextNode(text.slice(cursor, match.index)));
    const token = document.createElement("span");
    token.textContent = match[0];
    if (match[0].startsWith("#")) token.className = "syntax-comment";
    else if (match[0].startsWith("\"") || match[0].startsWith("'")) token.className = "syntax-string";
    else if (/^\d/.test(match[0])) token.className = "syntax-number";
    else token.className = "syntax-keyword";
    container.append(token);
    cursor = match.index + match[0].length;
  }
  container.append(document.createTextNode(text.slice(cursor)));
}

async function renderSource(value) {
  const token = ++state.sourceToken;
  const reference = $("#source-reference");
  const lines = $("#source-lines");
  const repository = $("#source-repository");
  const ref = sourceRefFor(value);
  if (!ref?.source_uid || !ref.file) {
    reference.textContent = state.current?.sources?.length ? "Select a module, operation, or source file" : "Source unavailable";
    lines.replaceChildren();
    repository.hidden = true;
    return;
  }
  reference.textContent = `${ref.file}:${ref.executed_line || ref.start_line} · ${ref.symbol || value.target || "source"}`;
  const source = await ensureSourceAsset(ref.source_uid);
  if (token !== state.sourceToken) return;
  if (!source) {
    lines.textContent = "Local source asset unavailable.";
    repository.hidden = true;
    return;
  }
  const text = await store.sourceText(source);
  if (token !== state.sourceToken) return;
  state.currentSourceText = text;
  state.currentSourceRef = { ...ref };
  const startLine = ref.start_line || 1;
  const endLine = ref.end_line || startLine;
  if (source.repository_file_url) {
    repository.href = `${source.repository_file_url}#L${startLine}-L${endLine}`;
    repository.hidden = false;
  } else repository.hidden = true;
  const traceLines = new Map((state.trace?.line_traces || []).filter((item) => item.file === ref.file).map((item) => [item.line, item]));
  const fragment = document.createDocumentFragment();
  const sourceLines = text.split("\n");
  sourceLines.forEach((lineText, index) => {
    const lineNumber = index + 1;
    const traceLine = traceLines.get(lineNumber);
    const row = document.createElement("button");
    row.className = `source-code-line${traceLine?.executed ? " executed" : ""}${lineNumber === (ref.executed_line || startLine) ? " active" : ""}`;
    row.dataset.line = lineNumber;
    const number = document.createElement("span");
    number.className = "line-number";
    number.textContent = lineNumber;
    const code = document.createElement("span");
    code.className = "line-code";
    appendHighlightedCode(code, lineText || " ");
    row.append(number, code);
    row.addEventListener("click", async () => {
      state.currentSourceRef = { ...ref, start_line: lineNumber, end_line: lineNumber, executed_line: lineNumber };
      const opId = traceLine?.op_ids?.[0];
      if (opId) await selectOperation(opId);
      else syncRoute();
      lines.querySelectorAll(".source-code-line.active").forEach((item) => item.classList.remove("active"));
      row.classList.add("active");
    });
    fragment.append(row);
  });
  lines.replaceChildren(fragment);
  renderSourceTree();
  requestAnimationFrame(() => lines.querySelector(".source-code-line.active")?.scrollIntoView({ block: "center" }));
  syncRoute({ push: false });
}

async function selectOperation(operationId) {
  if (state.mode !== "operation") await setMode("operation", { sync: false });
  let item = state.graphView.nodes.find((node) => node.id === operationId);
  if (!item) {
    const operation = state.graph?.nodes.find((node) => node.id === operationId);
    if (operation?.module_id) {
      state.scopeModuleId = operation.module_id;
      state.hierarchyModuleId = operation.module_id;
      expandModuleAncestors(moduleById(operation.module_id));
      await renderMode({ fit: true });
      item = state.graphView.nodes.find((node) => node.id === operationId);
    }
  }
  if (item) selectNode(item);
}

async function switchInspectorPanel(panel) {
  document.querySelectorAll(".inspector-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panel));
  document.querySelectorAll(".inspector-panel").forEach((section) => section.classList.toggle("active", section.id === `${panel}-panel`));
  if (panel === "source") await renderSource(state.inspected);
  if (panel === "config" && state.current) {
    $("#config-view").textContent = "Loading config...";
    try {
      state.config ||= await store.config(state.current);
      const fragment = document.createDocumentFragment();
      for (const [key, value] of [...flattenConfig(state.config)].slice(0, 1000)) {
        const row = document.createElement("div");
        row.className = "config-row";
        const name = document.createElement("span");
        name.className = "config-key";
        name.textContent = key;
        const content = document.createElement("span");
        content.className = "config-value";
        content.textContent = String(value);
        row.append(name, content);
        fragment.append(row);
      }
      $("#config-view").replaceChildren(fragment);
    } catch (error) {
      $("#config-view").textContent = error.message;
    }
  }
}

function updateDensityButton() {
  const button = $("#density-button");
  button.classList.toggle("active", state.mode === "operation");
  button.textContent = state.mode === "operation" ? "⊟" : "⊞";
  button.title = state.mode === "operation" ? "Collapse to module topology" : "Expand operation topology";
  button.disabled = state.mode === "family";
}

async function toggleDensity() {
  if (state.mode === "family") return;
  await setMode(state.mode === "operation" ? "module" : "operation");
}

function updateTransform() {
  $("#graph-canvas").style.transform = `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
  $("#zoom-value").value = `${Math.round(state.zoom * 100)}%`;
  scheduleVisibleRender();
}

function setZoom(next, origin = null) {
  const previous = state.zoom;
  state.zoom = Math.min(2.4, Math.max(0.16, next));
  if (origin) {
    state.pan.x = origin.x - ((origin.x - state.pan.x) * state.zoom) / previous;
    state.pan.y = origin.y - ((origin.y - state.pan.y) * state.zoom) / previous;
  }
  updateTransform();
}

function fitGraph() {
  if (!state.graphView.nodes.length) return;
  const viewport = $("#graph-viewport").getBoundingClientRect();
  state.bounds = graphBounds(state.graphView.nodes, allPositions());
  state.zoom = Math.min(1.1, Math.max(0.16, Math.min(viewport.width / state.bounds.width, viewport.height / state.bounds.height) * 0.9));
  state.pan = {
    x: Math.max(14, (viewport.width - state.bounds.width * state.zoom) / 2),
    y: Math.max(14, (viewport.height - state.bounds.height * state.zoom) / 2),
  };
  updateTransform();
}

function centerSelection() {
  if (!state.selectedId) return;
  const position = positionFor(state.selectedId);
  const viewport = $("#graph-viewport").getBoundingClientRect();
  state.pan = {
    x: viewport.width / 2 - (position.x + NODE_WIDTH / 2) * state.zoom,
    y: viewport.height / 2 - (position.y + NODE_HEIGHT / 2) * state.zoom,
  };
  updateTransform();
}

function resetLayout() {
  localStorage.removeItem(positionStorageKey());
  state.userPositions = new Map();
  state.pan = { x: 24, y: 24 };
  state.zoom = 1;
  renderMode({ fit: true });
}

function startNodeDrag(event) {
  if (event.button !== 0) return;
  event.stopPropagation();
  const node = event.currentTarget;
  const id = node.dataset.id;
  const start = { x: event.clientX, y: event.clientY };
  const initial = positionFor(id);
  node.setPointerCapture(event.pointerId);
  const move = (next) => {
    const position = {
      x: Math.max(0, initial.x + (next.clientX - start.x) / state.zoom),
      y: Math.max(0, initial.y + (next.clientY - start.y) / state.zoom),
    };
    state.userPositions.set(id, position);
    node.style.left = `${position.x}px`;
    node.style.top = `${position.y}px`;
    scheduleVisibleRender();
  };
  const end = () => {
    node.removeEventListener("pointermove", move);
    saveUserPositions();
  };
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", end, { once: true });
  node.addEventListener("pointercancel", end, { once: true });
}

function beginViewportGesture(event) {
  if (event.target.closest(".graph-node") || event.button !== 0) return;
  const viewport = $("#graph-viewport");
  state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  viewport.setPointerCapture(event.pointerId);
  if (state.pointers.size === 1) {
    state.gesture = { type: "pan", x: event.clientX, y: event.clientY, pan: { ...state.pan } };
    viewport.classList.add("panning");
  } else if (state.pointers.size === 2) {
    const [a, b] = [...state.pointers.values()];
    const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    state.gesture = {
      type: "pinch",
      distance: Math.hypot(a.x - b.x, a.y - b.y),
      zoom: state.zoom,
      world: { x: (midpoint.x - state.pan.x) / state.zoom, y: (midpoint.y - state.pan.y) / state.zoom },
    };
  }
}

function moveViewportGesture(event) {
  if (!state.pointers.has(event.pointerId)) return;
  state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (state.pointers.size === 2) {
    const [a, b] = [...state.pointers.values()];
    const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    if (state.gesture?.type !== "pinch") return;
    const distance = Math.hypot(a.x - b.x, a.y - b.y);
    state.zoom = Math.min(2.4, Math.max(0.16, state.gesture.zoom * distance / state.gesture.distance));
    state.pan = {
      x: midpoint.x - state.gesture.world.x * state.zoom,
      y: midpoint.y - state.gesture.world.y * state.zoom,
    };
  } else if (state.gesture?.type === "pan") {
    state.pan = {
      x: state.gesture.pan.x + event.clientX - state.gesture.x,
      y: state.gesture.pan.y + event.clientY - state.gesture.y,
    };
  }
  updateTransform();
}

function endViewportGesture(event) {
  state.pointers.delete(event.pointerId);
  if (state.pointers.size === 0) {
    state.gesture = null;
    $("#graph-viewport").classList.remove("panning");
  } else if (state.pointers.size === 1) {
    const [point] = state.pointers.values();
    state.gesture = { type: "pan", x: point.x, y: point.y, pan: { ...state.pan } };
  }
}

function beginTouchGesture(event) {
  if (event.touches.length !== 2) return;
  event.preventDefault();
  const [first, second] = event.touches;
  const midpoint = { x: (first.clientX + second.clientX) / 2, y: (first.clientY + second.clientY) / 2 };
  state.gesture = {
    type: "touch-pinch",
    distance: Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY),
    zoom: state.zoom,
    world: { x: (midpoint.x - state.pan.x) / state.zoom, y: (midpoint.y - state.pan.y) / state.zoom },
  };
}

function moveTouchGesture(event) {
  if (event.touches.length !== 2 || state.gesture?.type !== "touch-pinch") return;
  event.preventDefault();
  const [first, second] = event.touches;
  const midpoint = { x: (first.clientX + second.clientX) / 2, y: (first.clientY + second.clientY) / 2 };
  const distance = Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
  state.zoom = Math.min(2.4, Math.max(0.16, state.gesture.zoom * distance / state.gesture.distance));
  state.pan = {
    x: midpoint.x - state.gesture.world.x * state.zoom,
    y: midpoint.y - state.gesture.world.y * state.zoom,
  };
  updateTransform();
}

function endTouchGesture() {
  if (state.gesture?.type === "touch-pinch") state.gesture = null;
}

function sourceFiles(trace) {
  return [...new Set(trace.operations.map((operation) => operation.source_ref?.file).filter(Boolean))].sort();
}

function delta(left, right) {
  if (typeof left !== "number" || typeof right !== "number") return left === right ? "same" : "different";
  const value = right - left;
  return `${value > 0 ? "+" : ""}${value.toLocaleString()}`;
}

function appendCompareTable(container, rows, leftTitle, rightTitle) {
  const table = document.createElement("table");
  table.className = "compare-table";
  const head = document.createElement("thead");
  const heading = document.createElement("tr");
  for (const title of ["Metric", leftTitle, rightTitle, "Difference"]) {
    const cell = document.createElement("th");
    cell.textContent = title;
    heading.append(cell);
  }
  head.append(heading);
  const body = document.createElement("tbody");
  for (const [label, left, right, difference = delta(left, right)] of rows) {
    const row = document.createElement("tr");
    for (const value of [label, left, right, difference]) {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    }
    body.append(row);
  }
  table.append(head, body);
  container.append(table);
}

async function openCompare() {
  const content = $("#compare-content");
  content.replaceChildren();
  $("#compare-pane").hidden = false;
  updateScrim();
  if (state.compareIds.length < 2) {
    content.textContent = "Select two models in the catalog to compare.";
    return;
  }
  try {
    const [left, right] = await Promise.all(state.compareIds.map((id) => store.version(id)));
    const [leftConfig, rightConfig, leftTrace, rightTrace] = await Promise.all([
      store.config(left), store.config(right), store.trace(left), store.trace(right),
    ]);
    appendCompareTable(content, [
      ["Version", left.version_id, right.version_id],
      ["Library", left.library, right.library],
      ["Parameters", left.parameters.total, right.parameters.total],
      ["Operations", left.operation_count, right.operation_count],
      ["Source files", sourceFiles(leftTrace).length, sourceFiles(rightTrace).length],
      ["Config fields changed", 0, configDifferences(leftConfig, rightConfig).length],
    ], left.family_name, right.family_name);
  } catch (error) {
    content.textContent = error.message;
  }
}

function closeCompare() { $("#compare-pane").hidden = true; updateScrim(); }

function toggleFocus() {
  document.body.classList.toggle("focus-canvas");
  $("#focus-button").classList.toggle("active", document.body.classList.contains("focus-canvas"));
  requestAnimationFrame(() => { fitGraph(); renderVisibleGraph(); });
}

async function start() {
  try {
    const { manifest, index } = await store.initialize();
    state.manifest = manifest;
    state.index = index;
    populateCategories();
    filterIndex();
    updateDensityButton();
    if (location.hash.includes("/version/")) await applyRoute(location.hash);
    else if (index.length) {
      await loadVersion(index[0].version_id, { sync: false });
      await setMode("module", { sync: false });
      syncRoute({ push: false });
    }
  } catch (error) {
    $("#empty-state").textContent = error.message;
  }
}

$("#search").addEventListener("input", filterIndex);
$("#category").addEventListener("change", filterIndex);
$("#sort").addEventListener("change", filterIndex);
$("#model-list").addEventListener("scroll", renderListWindow, { passive: true });
$("#module-search").addEventListener("input", renderModuleTree);
document.querySelectorAll(".navigator-tab").forEach((button) => button.addEventListener("click", () => switchNavigator(button.dataset.navigator)));
document.querySelectorAll(".mode").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
document.querySelectorAll(".inspector-tab").forEach((button) => button.addEventListener("click", () => switchInspectorPanel(button.dataset.panel)));
$("#uri-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await applyRoute($("#uri-input").value); } catch (error) { showStatus(error.message); }
});
$("#copy-source").addEventListener("click", async () => {
  if (!state.currentSourceText) return;
  try {
    await navigator.clipboard.writeText(state.currentSourceText);
  } catch {
    const temporary = document.createElement("textarea");
    temporary.value = state.currentSourceText;
    temporary.style.position = "fixed";
    temporary.style.opacity = "0";
    document.body.append(temporary);
    temporary.select();
    document.execCommand("copy");
    temporary.remove();
  }
});
$("#zoom-in").addEventListener("click", () => setZoom(state.zoom + 0.12));
$("#zoom-out").addEventListener("click", () => setZoom(state.zoom - 0.12));
$("#fit-button").addEventListener("click", fitGraph);
$("#reset-button").addEventListener("click", resetLayout);
$("#density-button").addEventListener("click", toggleDensity);
$("#focus-button").addEventListener("click", toggleFocus);
$("#center-selection").addEventListener("click", centerSelection);
$("#compare-button").addEventListener("click", openCompare);
$("#close-compare").addEventListener("click", closeCompare);
$("#menu-button").addEventListener("click", openSidebar);
$("#close-inspector").addEventListener("click", closeInspector);
$("#scrim").addEventListener("click", () => { closeSidebar(); closeInspector(); closeCompare(); });
$("#module-tree").addEventListener("keydown", handleModuleTreeKeydown);

const viewport = $("#graph-viewport");
viewport.addEventListener("pointerdown", beginViewportGesture);
viewport.addEventListener("pointermove", moveViewportGesture);
viewport.addEventListener("pointerup", endViewportGesture);
viewport.addEventListener("pointercancel", endViewportGesture);
viewport.addEventListener("touchstart", beginTouchGesture, { passive: false });
viewport.addEventListener("touchmove", moveTouchGesture, { passive: false });
viewport.addEventListener("touchend", endTouchGesture, { passive: true });
viewport.addEventListener("wheel", (event) => {
  event.preventDefault();
  const bounds = viewport.getBoundingClientRect();
  setZoom(state.zoom * (event.deltaY < 0 ? 1.09 : 0.91), { x: event.clientX - bounds.left, y: event.clientY - bounds.top });
}, { passive: false });
viewport.addEventListener("click", (event) => {
  if (event.target.closest(".graph-node")) return;
  state.selectedId = null;
  state.selectedCallId = null;
  state.selectedIds.clear();
  renderVisibleGraph();
  syncRoute();
});
$("#minimap").addEventListener("click", (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  const worldX = (event.clientX - rect.left) / rect.width * state.bounds.width;
  const worldY = (event.clientY - rect.top) / rect.height * state.bounds.height;
  const view = viewport.getBoundingClientRect();
  state.pan = { x: view.width / 2 - worldX * state.zoom, y: view.height / 2 - worldY * state.zoom };
  updateTransform();
});
window.addEventListener("hashchange", () => applyRoute(location.hash).catch((error) => showStatus(error.message)));
window.addEventListener("resize", scheduleVisibleRender);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closeSidebar(); closeInspector(); closeCompare(); }
  if (event.key === "0" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); fitGraph(); }
});

start();
