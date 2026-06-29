import { configDifferences, flattenConfig, ModelStore } from "./data-store.js";
import { graphBounds, layoutGraph, projectGraph } from "./graph-model.js";

const $ = (selector) => document.querySelector(selector);
const store = new ModelStore();
const NODE_WIDTH = 196;
const NODE_HEIGHT = 76;
const LIST_ROW_HEIGHT = 62;

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
  expanded: false,
  activeBlock: null,
  inspected: null,
  selectedId: null,
  selectedIds: new Set(),
  compareIds: [],
  graphView: { nodes: [], edges: [] },
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
};

function formatNumber(value) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(value || 0);
}

function shapeLabel(records = []) {
  return records.map((record) => record?.shape || record).filter(Array.isArray)
    .map((shape) => `[${shape.join(", ")}]`).join(" ");
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

function populateCategories() {
  const select = $("#category");
  const categories = [...new Set(state.index.map((item) => item.category))].sort();
  for (const category of categories) {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category.replace(" models", "");
    select.append(option);
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
  state.filtered.sort((a, b) => {
    if (sort === "parameters") return b.parameters - a.parameters || a.family_name.localeCompare(b.family_name);
    if (sort === "version") return a.version_id.localeCompare(b.version_id);
    if (sort === "sources") return b.source_count - a.source_count || a.family_name.localeCompare(b.family_name);
    return a.family_name.localeCompare(b.family_name) || a.version_id.localeCompare(b.version_id);
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
    row.dataset.versionId = item.version_id;

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
    open.addEventListener("click", () => loadVersion(item.version_id));

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

function positionStorageKey() {
  const block = state.activeBlock?.block_uid || "all";
  return `model-vis-layout:${state.current?.structure_key || "none"}:${state.mode}:${state.expanded}:${block}`;
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
  ];
  if (state.mode !== "family") crumbs.push({ label: state.current.version_id, action: () => setMode("version") });
  if (state.mode === "block" || state.mode === "source") {
    crumbs.push({ label: state.activeBlock?.qualified_name || "Blocks", action: () => {
      state.activeBlock = null;
      setMode("block");
    } });
  }
  if (state.mode === "source") crumbs.push({ label: "Operations", action: () => setMode("source") });
  crumbs.forEach((crumb, index) => {
    const button = document.createElement("button");
    button.className = `breadcrumb${index === crumbs.length - 1 ? " current" : ""}`;
    button.textContent = crumb.label;
    button.addEventListener("click", crumb.action);
    nav.append(button);
  });
}

async function ensureModeAssets() {
  if (!state.current) return;
  if (state.mode === "family") {
    state.family ||= await store.family(state.current.family_id);
    return;
  }
  if (state.mode === "version") {
    state.graph ||= await store.graph(state.current);
    return;
  }
  if (state.mode === "block") {
    const [blockAsset, trace] = await Promise.all([
      state.blocks ? Promise.resolve({ blocks: state.blocks }) : store.blocks(state.current),
      state.trace ? Promise.resolve(state.trace) : store.trace(state.current),
    ]);
    state.blocks = blockAsset.blocks;
    state.trace = trace;
    return;
  }
  if (state.mode === "source") state.trace ||= await store.trace(state.current);
}

async function loadVersion(versionId) {
  const token = ++state.loadToken;
  showStatus("Loading model metadata…");
  try {
    const version = await store.version(versionId);
    const family = await store.family(version.family_id);
    if (token !== state.loadToken) return;
    state.current = version;
    state.family = family;
    state.graph = null;
    state.blocks = null;
    state.trace = null;
    state.config = null;
    state.activeBlock = null;
    state.selectedId = null;
    state.selectedIds.clear();
    state.inspected = version;
    state.pan = { x: 24, y: 24 };
    state.zoom = 1;
    renderListWindow();
    renderBreadcrumbs();
    renderInspector(version);
    await renderMode({ fit: true });
    closeSidebar();
  } catch (error) {
    showStatus("");
    $("#empty-state").hidden = false;
    $("#empty-state").textContent = error.message;
  }
}

async function setMode(mode) {
  state.mode = mode;
  state.selectedId = null;
  state.selectedIds.clear();
  if (mode !== "block" && mode !== "source") state.activeBlock = null;
  document.querySelectorAll(".mode").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  renderBreadcrumbs();
  updateDensityButton();
  await renderMode({ fit: true });
}

async function renderMode({ fit = false } = {}) {
  if (!state.current) return;
  showStatus("Loading view…");
  try {
    await ensureModeAssets();
    state.graphView = projectGraph({
      mode: state.mode,
      current: state.current,
      family: state.family,
      index: state.index,
      graph: state.graph,
      blocks: state.blocks,
      trace: state.trace,
      expanded: state.expanded,
      activeBlock: state.activeBlock,
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
    showStatus("");
    updateTransform();
    renderVisibleGraph();
    if (fit) requestAnimationFrame(fitGraph);
  } catch (error) {
    showStatus("");
    $("#empty-state").hidden = false;
    $("#empty-state").textContent = error.message;
  }
}

function visibleNodeIds() {
  const viewport = $("#graph-viewport");
  const width = viewport.clientWidth || 900;
  const height = viewport.clientHeight || 650;
  const margin = 260;
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
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `${item.title}, ${item.subtitle}`);
    const title = document.createElement("div");
    title.className = "node-title";
    title.textContent = item.title;
    const shape = document.createElement("div");
    shape.className = "node-shape";
    shape.textContent = item.subtitle;
    node.append(title, shape);
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
  renderMinimap();
  const virtualized = visible.size < state.graphView.nodes.length;
  showStatus(virtualized ? `${visible.size} / ${state.graphView.nodes.length} nodes visible` : "");
}

function renderEdges(visible) {
  const svg = $("#edges");
  const fragment = document.createDocumentFragment();
  for (const edge of state.graphView.edges) {
    if (!visible.has(edge.source) || !visible.has(edge.target)) continue;
    const before = positionFor(edge.source);
    const after = positionFor(edge.target);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const startX = before.x + NODE_WIDTH / 2;
    const startY = before.y + NODE_HEIGHT;
    const endX = after.x + NODE_WIDTH / 2;
    const endY = after.y;
    const bend = Math.max(28, Math.abs(endY - startY) / 2);
    path.setAttribute("d", `M ${startX} ${startY} C ${startX} ${startY + bend}, ${endX} ${endY - bend}, ${endX} ${endY}`);
    path.classList.toggle("active", edge.source === state.selectedId || edge.target === state.selectedId);
    fragment.append(path);
  }
  svg.replaceChildren(fragment);
}

function renderMinimap() {
  const canvas = $("#minimap");
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  const scale = Math.min(canvas.width / state.bounds.width, canvas.height / state.bounds.height);
  context.fillStyle = "#7b8d82";
  for (const node of state.graphView.nodes) {
    const position = positionFor(node.id);
    context.fillRect(position.x * scale, position.y * scale, Math.max(3, NODE_WIDTH * scale), Math.max(2, 6 * scale));
  }
  const viewport = $("#graph-viewport");
  const left = Math.max(0, -state.pan.x / state.zoom);
  const top = Math.max(0, -state.pan.y / state.zoom);
  context.strokeStyle = "#08785d";
  context.lineWidth = 3;
  context.strokeRect(
    left * scale,
    top * scale,
    Math.min(state.bounds.width - left, viewport.clientWidth / state.zoom) * scale,
    Math.min(state.bounds.height - top, viewport.clientHeight / state.zoom) * scale,
  );
}

function selectNode(item, event = {}) {
  event.stopPropagation?.();
  if (event.ctrlKey || event.metaKey) {
    if (state.selectedIds.has(item.id)) state.selectedIds.delete(item.id);
    else state.selectedIds.add(item.id);
  } else {
    state.selectedIds.clear();
    state.selectedIds.add(item.id);
  }
  state.selectedId = item.id;
  state.inspected = item.raw;
  renderInspector(item.raw);
  renderVisibleGraph();
  if (window.innerWidth <= 1100) openInspector();
}

async function drillIntoNode(item, event = {}) {
  event.stopPropagation?.();
  if (state.mode === "family") {
    const versionId = item.id.startsWith("version:") ? item.id.slice(8) : state.current.version_id;
    await loadVersion(versionId);
    await setMode("version");
    return;
  }
  if (state.mode === "version") {
    const qualified = item.raw.qualified_name;
    if (!state.blocks) state.blocks = (await store.blocks(state.current)).blocks;
    state.activeBlock = qualified
      ? state.blocks.filter((block) => qualified === block.qualified_name || qualified.startsWith(`${block.qualified_name}.`))
        .sort((a, b) => b.qualified_name.length - a.qualified_name.length)[0] || null
      : null;
    await setMode("block");
    return;
  }
  if (state.mode === "block" && item.raw.block_uid) {
    state.activeBlock = item.raw;
    renderBreadcrumbs();
    await renderMode({ fit: true });
    return;
  }
  if (state.mode === "block") await setMode("source");
}

function metadataRows(value) {
  const preferred = [
    "status", "library", "architecture_key", "entrypoint_class", "execution_mode", "kind", "target",
    "qualified_name", "block_type", "dedup_ref", "trace_confidence", "operation_count", "block_count",
  ];
  const rows = [];
  for (const key of preferred) {
    if (value?.[key] !== undefined && value[key] !== null) rows.push([key.replaceAll("_", " "), value[key]]);
  }
  if (value?.parameters !== undefined) {
    const count = typeof value.parameters === "number" ? value.parameters : value.parameters.total;
    rows.push(["parameters", count.toLocaleString()]);
  }
  if (value?.sources) rows.push(["source assets", value.sources.length]);
  if (value?.config_conditions) {
    rows.push(["config branches", value.config_conditions.length ? value.config_conditions.join(", ") : "none observed"]);
  }
  if (value?.pointer) rows.push(["block storage", `${value.pointer.type} → ${value.pointer.target_dedup_uid.slice(-12)}`]);
  const output = shapeLabel(value?.outputs || value?.output_shapes || value?.top_level_outputs);
  if (output) rows.push(["output", output]);
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
  renderSource(value);
}

function normalizeShapeRecords(value) {
  const records = [];
  for (const [role, items] of [["input", value?.inputs || value?.input_shapes || []], ["output", value?.outputs || value?.output_shapes || value?.top_level_outputs || []]]) {
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
    empty.textContent = "No observed tensor shape is attached to this selection.";
    fragment.append(empty);
  }
  for (const record of records) {
    const row = document.createElement("div");
    row.className = "shape-record";
    const role = document.createElement("div");
    role.className = "shape-role";
    role.textContent = record.role;
    const shape = document.createElement("div");
    shape.className = "shape-value";
    shape.textContent = `[${record.shape.join(", ")}]`;
    const meta = document.createElement("div");
    meta.className = "shape-meta";
    meta.textContent = [record.dtype, record.device, record.source].filter(Boolean).join(" · ");
    row.append(role, shape, meta);
    fragment.append(row);
  }
  $("#shape-list").replaceChildren(fragment);
}

function renderSource(value) {
  const reference = $("#source-reference");
  const lines = $("#source-lines");
  lines.replaceChildren();
  const ref = value?.source_ref || value?.source_refs?.[0];
  if (!ref?.file) {
    const count = state.current?.sources?.length || 0;
    reference.textContent = count ? `${count} source assets referenced by this model; select a module or operation.` : "Source reference unavailable";
    return;
  }
  reference.textContent = `${ref.file}:${ref.executed_line || ref.start_line} · ${ref.symbol || value.target}`;
  const operations = new Map((state.trace?.operations || []).map((operation) => [operation.op_id, operation]));
  const related = (state.trace?.line_traces || []).filter((line) => (
    line.file === ref.file && line.line >= ref.start_line && line.line <= ref.end_line
  ));
  for (const item of related) {
    const row = document.createElement("button");
    row.className = `source-line${item.op_ids.includes(value.op_id) ? " active" : ""}`;
    const number = document.createElement("span");
    number.className = "line-number";
    number.textContent = item.line;
    const detail = document.createElement("span");
    detail.className = "line-detail";
    detail.textContent = item.op_ids.map((id) => operations.get(id)?.display_name || id).join(", ") || "executed";
    const shapes = document.createElement("span");
    shapes.className = "line-shape";
    const input = shapeLabel(item.input_shapes);
    const output = shapeLabel(item.output_shapes);
    shapes.textContent = [input && `in ${input}`, output && `out ${output}`].filter(Boolean).join(" → ");
    detail.append(shapes);
    row.append(number, detail);
    row.addEventListener("click", () => item.op_ids[0] && selectOperation(item.op_ids[0]));
    lines.append(row);
  }
}

async function selectOperation(operationId) {
  if (state.mode !== "source") await setMode("source");
  const item = state.graphView.nodes.find((node) => node.id === operationId);
  if (item) selectNode(item);
}

async function switchInspectorPanel(panel) {
  document.querySelectorAll(".inspector-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panel));
  document.querySelectorAll(".inspector-panel").forEach((section) => section.classList.toggle("active", section.id === `${panel}-panel`));
  if (panel === "config" && state.current) {
    $("#config-view").textContent = "Loading config…";
    try {
      state.config ||= await store.config(state.current);
      const fragment = document.createDocumentFragment();
      const entries = [...flattenConfig(state.config)].slice(0, 500);
      for (const [key, value] of entries) {
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
  button.classList.toggle("active", state.expanded);
  button.textContent = state.expanded ? "⊟" : "⊞";
  button.title = state.expanded ? "Collapse to module calls" : "Expand Torchview graph detail";
  button.disabled = state.mode !== "version";
}

async function toggleDensity() {
  if (state.mode !== "version") return;
  state.expanded = !state.expanded;
  updateDensityButton();
  await renderMode({ fit: true });
}

function updateTransform() {
  $("#graph-canvas").style.transform = `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
  $("#zoom-value").value = `${Math.round(state.zoom * 100)}%`;
  scheduleVisibleRender();
}

function setZoom(next, origin = null) {
  const previous = state.zoom;
  state.zoom = Math.min(2.4, Math.max(0.18, next));
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
  state.zoom = Math.min(1.15, Math.max(0.18, Math.min(viewport.width / state.bounds.width, viewport.height / state.bounds.height) * 0.9));
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
    state.zoom = Math.min(2.4, Math.max(0.18, state.gesture.zoom * distance / state.gesture.distance));
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

function sourceFiles(trace) {
  return [...new Set(trace.operations.map((operation) => operation.source_ref?.file).filter(Boolean))].sort();
}

function outputShape(version) {
  return shapeLabel(version.top_level_outputs) || "—";
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
      if (value === difference) cell.className = "compare-delta";
      row.append(cell);
    }
    body.append(row);
  }
  table.append(head, body);
  container.append(table);
}

async function renderModelComparison() {
  const content = $("#compare-content");
  content.replaceChildren();
  if (state.compareIds.length < 2) {
    const empty = document.createElement("div");
    empty.className = "compare-empty";
    empty.textContent = "Select two models in the catalog to compare.";
    content.append(empty);
    return;
  }
  const [left, right] = await Promise.all(state.compareIds.map((id) => store.version(id)));
  const [leftConfig, rightConfig, leftTrace, rightTrace, leftBlocks, rightBlocks] = await Promise.all([
    store.config(left), store.config(right), store.trace(left), store.trace(right), store.blocks(left), store.blocks(right),
  ]);
  const leftDedup = new Set(leftBlocks.blocks.map((block) => block.dedup_ref));
  const rightDedup = new Set(rightBlocks.blocks.map((block) => block.dedup_ref));
  const shared = [...leftDedup].filter((id) => rightDedup.has(id)).length;
  const differences = configDifferences(leftConfig, rightConfig);
  appendCompareTable(content, [
    ["Version", left.version_id, right.version_id],
    ["Library", left.library, right.library],
    ["Parameters", left.parameters.total, right.parameters.total],
    ["Blocks", left.block_count, right.block_count],
    ["Operations", left.operation_count, right.operation_count],
    ["Output shapes", outputShape(left), outputShape(right)],
    ["Source files", sourceFiles(leftTrace).length, sourceFiles(rightTrace).length],
    ["Execution", left.execution_mode, right.execution_mode],
    ["Structure", left.structure_key.slice(-12), right.structure_key.slice(-12), left.structure_key === right.structure_key ? "same" : "different"],
    ["Shared block signatures", leftDedup.size, rightDedup.size, shared],
    ["Config fields changed", 0, differences.length, differences.length],
  ], left.family_name, right.family_name);
  const section = document.createElement("section");
  section.className = "config-diff";
  const title = document.createElement("h3");
  title.textContent = `Config differences (${differences.length})`;
  section.append(title);
  appendCompareTable(section, differences.slice(0, 20).map((item) => [item.key, item.left, item.right, "changed"]), left.version_id, right.version_id);
  content.append(section);
}

function blockOperationCount(block) {
  const prefix = `${block.qualified_name}.`;
  return (state.trace?.operations || []).filter((operation) => (
    operation.qualified_name === block.qualified_name || operation.qualified_name.startsWith(prefix)
  )).length;
}

function renderBlockComparison(blocks) {
  const content = $("#compare-content");
  content.replaceChildren();
  const [left, right] = blocks;
  appendCompareTable(content, [
    ["Block type", left.block_type, right.block_type],
    ["Qualified name", left.qualified_name, right.qualified_name],
    ["Operations", blockOperationCount(left), blockOperationCount(right)],
    ["Dedup signature", left.dedup_ref.slice(-12), right.dedup_ref.slice(-12), left.dedup_ref === right.dedup_ref ? "shared" : "different"],
    ["Storage", left.pointer.type, right.pointer.type],
    ["Source", left.source_refs[0]?.file || "—", right.source_refs[0]?.file || "—"],
  ], left.qualified_name, right.qualified_name);
}

async function openCompare() {
  const selectedBlocks = state.graphView.nodes.filter((node) => state.selectedIds.has(node.id) && node.raw.block_uid).map((node) => node.raw);
  $("#compare-pane").hidden = false;
  updateScrim();
  try {
    if (state.mode === "block" && selectedBlocks.length === 2) renderBlockComparison(selectedBlocks);
    else await renderModelComparison();
  } catch (error) {
    $("#compare-content").textContent = error.message;
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
    if (index.length) await loadVersion(index[0].version_id);
  } catch (error) {
    $("#empty-state").textContent = error.message;
  }
}

$("#search").addEventListener("input", filterIndex);
$("#category").addEventListener("change", filterIndex);
$("#sort").addEventListener("change", filterIndex);
$("#model-list").addEventListener("scroll", renderListWindow, { passive: true });
document.querySelectorAll(".mode").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
document.querySelectorAll(".inspector-tab").forEach((button) => button.addEventListener("click", () => switchInspectorPanel(button.dataset.panel)));
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

const viewport = $("#graph-viewport");
viewport.addEventListener("pointerdown", beginViewportGesture);
viewport.addEventListener("pointermove", moveViewportGesture);
viewport.addEventListener("pointerup", endViewportGesture);
viewport.addEventListener("pointercancel", endViewportGesture);
viewport.addEventListener("wheel", (event) => {
  event.preventDefault();
  const bounds = viewport.getBoundingClientRect();
  setZoom(state.zoom * (event.deltaY < 0 ? 1.09 : 0.91), { x: event.clientX - bounds.left, y: event.clientY - bounds.top });
}, { passive: false });
viewport.addEventListener("click", (event) => {
  if (event.target.closest(".graph-node")) return;
  state.selectedId = null;
  state.selectedIds.clear();
  renderVisibleGraph();
});
$("#minimap").addEventListener("click", (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  const worldX = (event.clientX - rect.left) / rect.width * state.bounds.width;
  const worldY = (event.clientY - rect.top) / rect.height * state.bounds.height;
  const view = viewport.getBoundingClientRect();
  state.pan = { x: view.width / 2 - worldX * state.zoom, y: view.height / 2 - worldY * state.zoom };
  updateTransform();
});
window.addEventListener("resize", scheduleVisibleRender);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closeSidebar(); closeInspector(); closeCompare(); }
  if (event.key === "0" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); fitGraph(); }
});

start();
