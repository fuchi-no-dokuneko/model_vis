import { configDifferences, flattenConfig, ModelStore } from "./data-store.js";
import {
  graphBounds, graphSafeRect, intervalsForEdge, layoutGraph, NODE_HEIGHT, NODE_WIDTH,
  parseViewerRoute, placeMarkers1D, projectGraph, semanticZoomTier, tracePath,
} from "./graph-model.js";

const $ = (selector) => document.querySelector(selector);
const store = new ModelStore();
const LIST_ROW_HEIGHT = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--model-row-height")) || 70;
const MIN_NODE_WIDTH = 184;
const MIN_NODE_HEIGHT = 132;
const STAGE_NODE_HEIGHT = 196;
const MAX_NODE_WIDTH = 960;
const MAX_NODE_HEIGHT = 720;
const LAYER_COLORS = [
  "#08785d", "#356a9b", "#a76508", "#8a4f79", "#577b2f", "#a5483f",
  "#4f6f87", "#7a5d25", "#4b8079", "#76558c", "#87603f", "#3d737e",
];
const VIEWPORT_PAN_DRAG_THRESHOLD = 4;

const state = {
  manifest: null,
  index: [],
  filtered: [],
  mode: "family",
  detailMode: "beginner",
  labelMode: "semantic",
  current: null,
  family: null,
  graph: null,
  blocks: null,
  trace: null,
  config: null,
  officialConfig: null,
  traceConfig: null,
  configDiff: null,
  semantic: null,
  configMode: "official",
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
  userSizes: new Map(),
  layoutKey: "",
  bounds: { width: 1200, height: 800 },
  zoom: 1,
  pan: { x: 24, y: 24 },
  pointers: new Map(),
  gesture: null,
  renderFrame: null,
  geometryFrame: null,
  loadToken: 0,
  sourceToken: 0,
  sourceAssets: new Map(),
  currentSourceText: "",
  currentSourceRef: null,
  moduleExpanded: new Set(["module-00000"]),
  fileExpanded: new Set(),
  routeApplying: false,
  graphQuery: "",
  graphMatches: new Set(),
  pathMode: null,
  pathNodes: new Set(),
  pathEdges: new Set(),
  selectedPortId: null,
  selectedStageId: null,
  selectedTag: null,
  activeJourney: null,
  collapsedStages: new Set(),
  pendingSelection: null,
  viewportDrag: { started: false, startX: 0, startY: 0 },
  overlayState: { legend: true, minimap: true },
};

function savedViewState() {
  try { return JSON.parse(localStorage.getItem("model-vis-view-state") || "null") || {}; }
  catch { return {}; }
}

function persistViewState() {
  if (!state.current) return;
  localStorage.setItem("model-vis-view-state", JSON.stringify({
    versionId: state.current.version_id,
    primaryView: state.mode,
    detailMode: state.detailMode,
    labelMode: state.labelMode,
    selectedId: state.selectedId,
    selectedStageId: state.selectedStageId,
  }));
}

function initializeViewPreferences() {
  const saved = savedViewState();
  if (["beginner", "standard", "trace"].includes(saved.detailMode)) state.detailMode = saved.detailMode;
  if (["semantic", "both", "source"].includes(saved.labelMode)) state.labelMode = saved.labelMode;
  document.body.dataset.detailMode = state.detailMode;
  $("#detail-mode").value = state.detailMode;
  $("#label-mode").value = state.labelMode;
}

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

function showTransientStatus(message) {
  showStatus(message);
  window.setTimeout(() => {
    if ($("#graph-status").textContent === message) showStatus("");
  }, 1600);
}

function applyTheme(theme, { persist = true } = {}) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  if (persist) localStorage.setItem("model-vis-theme", next);
  const button = $("#theme-button");
  button.setAttribute("aria-pressed", String(next === "dark"));
  button.setAttribute("aria-label", `Switch to ${next === "dark" ? "light" : "dark"} theme`);
  button.title = `Switch to ${next === "dark" ? "light" : "dark"} theme`;
  button.textContent = next === "dark" ? "☀" : "◐";
  if (state.graphView.nodes.length) renderMinimap();
}

function initializeTheme() {
  const stored = localStorage.getItem("model-vis-theme");
  const preferred = window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  applyTheme(stored || preferred, { persist: false });
}

function setTooltip(element, text) {
  if (!element || !text) return;
  element.dataset.tooltip = text;
  element.setAttribute("aria-describedby", "ui-tooltip");
}

function showTooltip(element) {
  const tooltip = $("#ui-tooltip");
  const text = element?.dataset?.tooltip;
  if (!text) return;
  tooltip.textContent = text;
  tooltip.hidden = false;
  const rect = element.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  tooltip.style.left = `${Math.max(8, Math.min(window.innerWidth - tooltipRect.width - 8, rect.left))}px`;
  tooltip.style.top = `${Math.max(8, rect.top - tooltipRect.height - 7)}px`;
}

function hideTooltip() {
  $("#ui-tooltip").hidden = true;
}

function applyOverlayState({ persist = true } = {}) {
  for (const [name, expanded] of Object.entries(state.overlayState)) {
    const panel = name === "legend" ? $("#graph-legend") : $("#minimap-panel");
    const button = $(`#${name}-toggle`);
    panel.classList.toggle("collapsed", !expanded);
    button.setAttribute("aria-expanded", String(expanded));
    button.textContent = expanded ? "−" : "+";
    button.title = `${expanded ? "Collapse" : "Expand"} ${name}`;
  }
  if (persist) localStorage.setItem("model-vis-overlays", JSON.stringify(state.overlayState));
  if (state.graphView.nodes.length) requestAnimationFrame(() => {
    fitGraph();
    renderMinimap();
    renderEdges(visibleNodeIds());
  });
}

function initializeOverlayState() {
  try {
    const stored = JSON.parse(localStorage.getItem("model-vis-overlays") || "null");
    if (stored && typeof stored === "object") {
      state.overlayState.legend = stored.legend !== false;
      state.overlayState.minimap = stored.minimap !== false;
    }
  } catch {
    localStorage.removeItem("model-vis-overlays");
  }
  applyOverlayDefaultsForDetail();
  applyOverlayState({ persist: false });
}

function applyOverlayDefaultsForDetail() {
  if (localStorage.getItem("model-vis-overlays") !== null) return;
  const expanded = state.detailMode !== "beginner";
  state.overlayState.legend = expanded;
  state.overlayState.minimap = expanded;
}

function graphOverlayRectangles() {
  const viewport = $("#graph-viewport").getBoundingClientRect();
  return ["#graph-legend", "#minimap-panel", "#graph-status"].flatMap((selector) => {
    const element = $(selector);
    if (!element || getComputedStyle(element).display === "none") return [];
    if (selector === "#graph-status" && element.hidden) {
      return [{ left: 12, top: 12, right: Math.min(viewport.width - 12, 320), bottom: 50,
        width: Math.min(viewport.width - 24, 308), height: 38,
        viewportWidth: viewport.width, viewportHeight: viewport.height }];
    }
    if (element.hidden) return [];
    const rect = element.getBoundingClientRect();
    return [{
      left: rect.left - viewport.left,
      top: rect.top - viewport.top,
      right: rect.right - viewport.left,
      bottom: rect.bottom - viewport.top,
      width: rect.width,
      height: rect.height,
      viewportWidth: viewport.width,
      viewportHeight: viewport.height,
    }];
  });
}

function getGraphSafeRect() {
  const viewport = $("#graph-viewport");
  return graphSafeRect({ width: viewport.clientWidth, height: viewport.clientHeight }, graphOverlayRectangles());
}

async function copyText(text, label) {
  if (!text) {
    showTransientStatus(`No ${label.toLowerCase()} is available for this selection`);
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const temporary = document.createElement("textarea");
    temporary.value = text;
    temporary.style.position = "fixed";
    temporary.style.opacity = "0";
    document.body.append(temporary);
    temporary.select();
    document.execCommand("copy");
    temporary.remove();
  }
  showTransientStatus(`${label} copied`);
  return true;
}

function selectedGraphValue() {
  return state.graphView.nodes.find((item) => item.id === state.selectedId)?.raw || state.inspected || null;
}

async function selectedSourceCode() {
  const ref = sourceRefFor(selectedGraphValue()) || state.currentSourceRef;
  if (!ref?.source_uid) return "";
  const source = await ensureSourceAsset(ref.source_uid);
  if (!source) return "";
  const text = await store.sourceText(source);
  const lines = text.split("\n");
  const start = Math.max(1, ref.start_line || ref.executed_line || 1);
  const end = Math.max(start, ref.end_line || ref.executed_line || start);
  return lines.slice(start - 1, end).join("\n");
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
  document.querySelectorAll(".navigator-tab").forEach((tab) => {
    const active = tab.dataset.navigator === panel;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
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
    if (item.status === "partial") {
      const warning = document.createElement("span");
      warning.className = "model-warning-badge";
      const warningText = item.warnings?.map((value) => value.message).join("\n") || "Partial model record";
      warning.title = warningText;
      setTooltip(warning, warningText);
      warning.setAttribute("aria-label", "Model has a warning");
      warning.textContent = "!";
      name.append(warning);
    }
    const meta = document.createElement("span");
    meta.className = "model-meta";
    const metadata = [
      [item.category.replace(" models", ""), "meta-label"],
      [item.version_id, "meta-value"],
      [`trace ${formatNumber(item.parameters)}`, "meta-label"],
      [item.official_parameter_estimate ? `official ${formatNumber(item.official_parameter_estimate)}` : "official —", "meta-value"],
    ];
    for (const [text, className] of metadata) {
      const value = document.createElement("span");
      value.className = className;
      value.textContent = text;
      meta.append(value);
    }
    const fullMetadata = `${item.category}; version ${item.version_id}; ${item.parameters.toLocaleString()} Trace parameters; ${item.official_parameter_estimate?.toLocaleString() || "no"} official estimate`;
    open.setAttribute("aria-label", `${item.family_name}. ${fullMetadata}`);
    setTooltip(open, fullMetadata);
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

function semanticEntityFor(value) {
  if (!state.semantic || !value) return null;
  const candidates = [value.entity_id, value.stage_id, value.id, value.module_id, value.block_uid].filter(Boolean);
  for (const id of candidates) if (state.semantic.entities?.[id]) return state.semantic.entities[id];
  return null;
}

function semanticStageFor(value = state.inspected) {
  if (!state.semantic) return null;
  if (value?.stage_id && state.semantic.stages.some((stage) => stage.stage_id === value.stage_id)) {
    return state.semantic.stages.find((stage) => stage.stage_id === value.stage_id);
  }
  const entity = semanticEntityFor(value);
  return state.semantic.stages.find((stage) => stage.stage_id === (entity?.stage_id || state.selectedStageId)) || null;
}

function moduleLabels(module) {
  const entity = semanticEntityFor(module);
  const source = module.qualified_name === "<root>" ? state.current?.family_name : module.qualified_name;
  if (!entity || state.labelMode === "source") return { primary: source, secondary: module.display_name };
  if (state.labelMode === "both") return { primary: entity.semantic_name, secondary: source };
  return { primary: entity.semantic_name, secondary: entity.primary_tag === "other" ? `${source} · Unclassified` : source };
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
  if (state.mode === "architecture" && state.selectedStageId) segments.push("stage", encodeURIComponent(state.selectedStageId));
  const scope = moduleById(state.scopeModuleId);
  if (state.mode !== "architecture" && scope && scope.qualified_name !== "<root>") segments.push("module", encodeURIComponent(scope.qualified_name));
  if (state.mode !== "architecture" && state.selectedCallId) segments.push("call", encodeURIComponent(state.selectedCallId));
  if (state.mode !== "architecture" && state.selectedId) segments.push("operation", encodeURIComponent(state.selectedId));
  if (state.currentSourceRef?.source_uid) {
    segments.push("source", encodeURIComponent(state.currentSourceRef.source_uid));
    if (state.currentSourceRef.executed_line) segments.push("line", String(state.currentSourceRef.executed_line));
  }
  segments.push("detail", state.detailMode, "labels", state.labelMode);
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

async function applyRoute(value) {
  const route = parseViewerRoute(value);
  if (route.detail && !["beginner", "standard", "trace"].includes(route.detail)) throw new Error(`Unknown detail mode: ${route.detail}`);
  if (route.labels && !["semantic", "both", "source"].includes(route.labels)) throw new Error(`Unknown label mode: ${route.labels}`);
  if (route.detail) state.detailMode = route.detail;
  if (route.labels) state.labelMode = route.labels;
  document.body.dataset.detailMode = state.detailMode;
  $("#detail-mode").value = state.detailMode;
  $("#label-mode").value = state.labelMode;
  applyOverlayDefaultsForDetail();
  applyOverlayState({ persist: false });
  if (route.compare) {
    if (route.compare.some((id) => !state.index.some((item) => item.version_id === id))) throw new Error("Compare route contains an unknown model version");
    state.compareIds = route.compare;
    await openCompare({ sync: false, view: route.view || "architecture" });
    history.replaceState(null, "", `${location.pathname}${location.search}#/${["compare", ...route.compare, "view", route.view || "architecture", "detail", state.detailMode, "labels", state.labelMode].map(encodeURIComponent).join("/")}`);
    return;
  }
  if (!route.version) throw new Error("URI must include /version/<version-id>");
  if (!state.index.some((item) => item.version_id === route.version)) throw new Error(`Unknown model version: ${route.version}`);
  if (route.view && !["architecture", "family", "module", "blocks", "operation"].includes(route.view)) {
    throw new Error(`Unknown graph detail mode: ${route.view}`);
  }
  state.routeApplying = true;
  try {
    await loadVersion(route.version, { sync: false });
    const mode = ["architecture", "family", "module", "blocks", "operation"].includes(route.view) ? route.view : "architecture";
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
    await switchInspectorPanel(state.detailMode === "beginner" ? "explain" : "details");
    if (route.stage) {
      const item = state.graphView.nodes.find((node) => node.id === route.stage);
      if (!item) throw new Error(`Unknown semantic stage: ${route.stage}`);
      selectNode(item, {}, { sync: false });
    } else if (route.operation) {
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
    const stored = JSON.parse(localStorage.getItem(positionStorageKey()) || "[]");
    if (Array.isArray(stored)) {
      state.userPositions = new Map(stored);
      state.userSizes = new Map();
    } else {
      state.userPositions = new Map(stored.positions || []);
      state.userSizes = new Map(stored.sizes || []);
    }
  } catch {
    state.userPositions = new Map();
    state.userSizes = new Map();
  }
}

function saveUserPositions() {
  localStorage.setItem(positionStorageKey(), JSON.stringify({
    positions: [...state.userPositions],
    sizes: [...state.userSizes],
  }));
}

function positionFor(id) {
  return state.userPositions.get(id) || state.basePositions.get(id) || { x: 40, y: 40 };
}

function sizeFor(id) {
  if (state.collapsedStages.has(id)) return { width: NODE_WIDTH, height: 74 };
  const item = state.graphView.nodes.find((node) => node.id === id);
  const stored = state.userSizes.get(id);
  if (stored) return item?.kind === "semantic_stage"
    ? { ...stored, height: Math.max(STAGE_NODE_HEIGHT, stored.height) }
    : stored;
  return { width: NODE_WIDTH, height: item?.kind === "semantic_stage" ? STAGE_NODE_HEIGHT : NODE_HEIGHT };
}

function allPositions() {
  return new Map(state.graphView.nodes.map((node) => [node.id, positionFor(node.id)]));
}

function allSizes() {
  return new Map(state.graphView.nodes.map((node) => [node.id, sizeFor(node.id)]));
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
  if (state.mode !== "architecture" && scope && scope.qualified_name !== "<root>") {
    const parts = scope.qualified_name.split(".");
    for (let index = 0; index < parts.length; index += 1) {
      const path = parts.slice(0, index + 1).join(".");
      const module = moduleByPath(path);
      if (module) crumbs.push({ label: state.labelMode === "source" ? parts[index] : moduleLabels(module).primary, action: () => selectModule(module.module_id) });
    }
  }
  if (state.mode === "architecture") {
    crumbs.push({ label: "Architecture", action: () => setMode("architecture") });
    const stage = state.semantic?.stages.find((item) => item.stage_id === state.selectedStageId);
    if (stage) crumbs.push({ label: state.labelMode === "source" ? stage.stage_type : stage.semantic_name, action: () => {} });
  }
  if (state.mode === "operation") crumbs.push({ label: "Operations", action: () => setMode("operation") });
  if (state.mode === "blocks") crumbs.push({ label: "Blocks", action: () => setMode("blocks") });
  const visibleCrumbs = crumbs.length > 5
    ? [crumbs[0], { overflow: crumbs.slice(1, -1) }, crumbs.at(-1)]
    : crumbs;
  visibleCrumbs.forEach((crumb, index) => {
    if (crumb.overflow) {
      const wrapper = document.createElement("span");
      wrapper.className = "breadcrumb-menu-wrap";
      const overflow = document.createElement("button");
      overflow.className = "breadcrumb breadcrumb-overflow";
      overflow.textContent = "…";
      overflow.setAttribute("aria-label", `Show ${crumb.overflow.length} middle locations`);
      setTooltip(overflow, crumb.overflow.map((item) => item.label).join(" / "));
      const menu = document.createElement("div");
      menu.className = "breadcrumb-menu";
      menu.hidden = true;
      for (const item of crumb.overflow) {
        const option = document.createElement("button");
        option.textContent = item.label;
        option.addEventListener("click", () => { menu.hidden = true; item.action(); });
        menu.append(option);
      }
      overflow.addEventListener("click", () => { menu.hidden = !menu.hidden; });
      overflow.addEventListener("click", () => {
        const rect = overflow.getBoundingClientRect();
        menu.style.left = `${Math.min(window.innerWidth - 328, rect.left)}px`;
        menu.style.top = `${rect.bottom + 4}px`;
      });
      wrapper.append(overflow, menu);
      nav.append(wrapper);
      return;
    }
    const button = document.createElement("button");
    button.className = `breadcrumb${index > 0 && index < visibleCrumbs.length - 1 ? " middle" : ""}${index === visibleCrumbs.length - 1 ? " current" : ""}`;
    button.textContent = crumb.label;
    button.setAttribute("aria-label", crumb.label);
    if (index === visibleCrumbs.length - 1) button.setAttribute("aria-current", "location");
    setTooltip(button, crumb.label);
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
  state.semantic ||= await store.semantic(state.current);
  if (state.mode === "blocks") state.blocks ||= await store.blocks(state.current);
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
  state.officialConfig = null;
  state.traceConfig = null;
  state.configDiff = null;
  state.semantic = null;
  state.configMode = "official";
  state.scopeModuleId = null;
  state.hierarchyModuleId = null;
  state.selectedId = null;
  state.selectedCallId = null;
  state.selectedIds.clear();
  state.pathMode = null;
  state.pathNodes.clear();
  state.pathEdges.clear();
  state.selectedPortId = null;
  state.selectedStageId = null;
  state.selectedTag = null;
  state.activeJourney = null;
  state.collapsedStages.clear();
  const saved = savedViewState();
  state.pendingSelection = saved.versionId === versionId ? saved : null;
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
  const preservedStage = semanticStageFor()?.stage_id || state.selectedStageId || state.pendingSelection?.selectedStageId;
  const preservedId = state.selectedId || state.pendingSelection?.selectedId;
  state.mode = mode;
  if (mode === "architecture") {
    const stage = state.semantic?.stages.find((value) => value.stage_id === preservedStage)
      || state.semantic?.stages[0] || null;
    state.scopeModuleId = state.graph?.modules[0]?.module_id || null;
    state.hierarchyModuleId = null;
    state.selectedStageId = stage?.stage_id || preservedStage || null;
    state.selectedId = state.selectedStageId;
    state.inspected = stage || state.current;
  }
  state.selectedCallId = null;
  state.selectedIds.clear();
  state.pathMode = null;
  state.pathNodes.clear();
  state.pathEdges.clear();
  state.selectedPortId = null;
  document.querySelectorAll(".mode").forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  updateDensityButton();
  await renderMode({ fit: true });
  let item = null;
  if (mode === "architecture" && preservedStage) {
    item = state.graphView.nodes.find((node) => node.id === preservedStage);
  } else if (mode !== "architecture") {
    item = state.graphView.nodes.find((node) => node.id === preservedId);
    const stage = state.semantic?.stages.find((value) => value.stage_id === preservedStage);
    if (!item && stage) {
      if (mode === "operation") item = state.graphView.nodes.find((node) => stage.operation_ids.includes(node.id));
      else item = state.graphView.nodes.find((node) => stage.module_ids.some((moduleId) => node.id === `group:${moduleId}` || node.raw?.module_id === moduleId));
    }
  }
  if (!item && mode === "architecture") item = state.graphView.nodes[0] || null;
  if (item) selectNode(item, {}, { sync: false, openOnMobile: false });
  else {
    state.selectedId = null;
    state.selectedStageId = preservedStage || null;
    renderVisibleGraph();
  }
  state.pendingSelection = null;
  persistViewState();
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
  document.querySelectorAll(".mode").forEach((button) => {
    const active = button.dataset.mode === state.mode;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
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
    const projectionMode = state.mode === "architecture" && !state.semantic ? "module" : state.mode;
    state.graphView = projectGraph({
      mode: projectionMode,
      current: state.current,
      family: state.family,
      index: state.index,
      graph: state.graph,
      blocks: state.blocks,
      semantic: state.semantic,
      labelMode: state.labelMode,
      scopeModuleId: state.scopeModuleId,
    });
    const nextLayoutKey = positionStorageKey();
    state.basePositions = layoutGraph(state.graphView.nodes, state.graphView.edges);
    if (state.layoutKey !== nextLayoutKey) {
      state.layoutKey = nextLayoutKey;
      loadUserPositions();
    }
    state.bounds = graphBounds(state.graphView.nodes, allPositions(), allSizes());
    $("#graph-canvas").style.width = `${state.bounds.width}px`;
    $("#graph-canvas").style.height = `${state.bounds.height}px`;
    $("#edges").setAttribute("viewBox", `0 0 ${state.bounds.width} ${state.bounds.height}`);
    $("#empty-state").hidden = state.graphView.nodes.length > 0;
    renderBreadcrumbs();
    updateGraphSearch({ render: false });
    updatePathControls();
    updateTransform();
    renderVisibleGraph();
    renderStructuralSummary();
    renderInspector(state.inspected);
    if (fit) requestAnimationFrame(fitGraph);
  } catch (error) {
    $("#empty-state").hidden = false;
    $("#empty-state").textContent = error.message;
  } finally {
    if ($("#graph-status").textContent === "Loading view...") showStatus("");
  }
}

async function setLabelMode(mode, { sync = true } = {}) {
  if (!["semantic", "both", "source"].includes(mode)) return;
  const selectedId = state.selectedId;
  state.labelMode = mode;
  $("#label-mode").value = mode;
  await renderMode();
  const item = state.graphView.nodes.find((node) => node.id === selectedId);
  if (item) selectNode(item, {}, { sync: false, openOnMobile: false });
  renderModuleTree();
  persistViewState();
  if (sync) syncRoute();
}

async function setDetailMode(mode, { sync = true } = {}) {
  if (!["beginner", "standard", "trace"].includes(mode)) return;
  state.detailMode = mode;
  if (mode === "beginner") state.labelMode = "semantic";
  if (mode === "standard") state.labelMode = "both";
  if (mode === "trace") state.labelMode = "source";
  document.body.dataset.detailMode = mode;
  $("#detail-mode").value = mode;
  $("#label-mode").value = state.labelMode;
  applyOverlayDefaultsForDetail();
  applyOverlayState({ persist: false });
  const targetMode = mode === "beginner" ? "architecture"
    : mode === "trace" && state.mode === "architecture" ? "operation" : state.mode;
  await setMode(targetMode, { sync: false });
  await switchInspectorPanel(mode === "beginner" ? "explain" : "details");
  persistViewState();
  if (sync) syncRoute();
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
    const labels = moduleLabels(module);
    label.textContent = labels.primary;
    const className = document.createElement("span");
    className.className = "tree-class";
    className.textContent = labels.secondary;
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
    const size = sizeFor(node.id);
    return position.x + size.width >= left && position.x <= right
      && position.y + size.height >= top && position.y <= bottom;
  }).map((node) => node.id));
}

function scheduleVisibleRender() {
  if (state.renderFrame !== null) return;
  state.renderFrame = requestAnimationFrame(() => {
    state.renderFrame = null;
    renderVisibleGraph();
  });
}

function updateCanvasGeometry() {
  state.bounds = graphBounds(state.graphView.nodes, allPositions(), allSizes());
  $("#graph-canvas").style.width = `${state.bounds.width}px`;
  $("#graph-canvas").style.height = `${state.bounds.height}px`;
  $("#edges").setAttribute("viewBox", `0 0 ${state.bounds.width} ${state.bounds.height}`);
  renderEdges(visibleNodeIds());
  renderLayerGroups();
  renderMinimap();
}

function scheduleGeometryRender() {
  if (state.geometryFrame !== null) return;
  state.geometryFrame = requestAnimationFrame(() => {
    state.geometryFrame = null;
    updateCanvasGeometry();
  });
}

function portBand(nodeItem, ports, direction) {
  const band = document.createElement("div");
  band.className = `node-ports ${direction === "input" ? "inputs" : "outputs"}`;
  if (!ports.length) {
    const empty = document.createElement("span");
    empty.className = "node-port";
    band.append(empty);
    return band;
  }
  for (const port of ports) {
    const portElement = document.createElement("div");
    portElement.className = "node-port";
    portElement.dataset.portId = port.port_id;
    portElement.classList.toggle("selected", state.selectedPortId === port.port_id);
    portElement.title = [
      port.name || direction,
      shapeLabel([port]),
      port.dtype,
      port.device,
      port.required ? "required" : "optional",
      port.alias_kind,
    ].filter(Boolean).join(" · ");
    setTooltip(portElement, portElement.title);
    const name = document.createElement("span");
    name.className = "port-name";
    name.textContent = port.name || `${direction} ${port.index}`;
    const shape = document.createElement("span");
    shape.className = "port-shape";
    shape.textContent = shapeLabel([port]) || "non-tensor";
    const meta = document.createElement("span");
    meta.className = "port-meta";
    meta.textContent = [port.dtype?.replace("torch.", ""), port.alias_kind, port.is_inplace ? "mutated" : null].filter(Boolean).join(" · ");
    portElement.append(name, shape, meta);
    portElement.addEventListener("pointerdown", (event) => event.stopPropagation());
    portElement.addEventListener("click", (event) => selectPort(nodeItem, port, direction, event));
    band.append(portElement);
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
    node.dataset.confidence = item.raw.confidence || "";
    node.classList.toggle("stage-collapsed", state.collapsedStages.has(item.id));
    node.classList.toggle("selected", state.selectedId === item.id);
    node.classList.toggle("multi-selected", state.selectedIds.has(item.id));
    node.classList.toggle("search-match", state.graphMatches.has(item.id));
    node.classList.toggle("path-active", state.pathNodes.has(item.id));
    node.classList.toggle("path-muted", state.pathNodes.size > 0 && !state.pathNodes.has(item.id));
    node.style.left = `${position.x}px`;
    node.style.top = `${position.y}px`;
    const size = sizeFor(item.id);
    node.style.width = `${size.width}px`;
    node.style.height = `${size.height}px`;
    node.style.setProperty("--layer-color", layerColor(item.layerGroupId));
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    const exactIdentity = item.raw.qualified_name || item.raw.module_path || item.raw.source_name || item.title;
    node.setAttribute("aria-label", `${item.title}, source ${exactIdentity}, ${item.inputPorts.length} inputs, ${item.outputPorts.length} outputs${item.raw.confidence ? `, ${item.raw.confidence}` : ""}`);
    setTooltip(node, exactIdentity === item.title ? item.title : `${item.title} · ${exactIdentity}`);
    const core = document.createElement("div");
    core.className = "node-core";
    const heading = document.createElement("div");
    heading.className = "node-heading node-drag-handle";
    const title = document.createElement("div");
    title.className = "node-title";
    title.textContent = item.title;
    const subtitle = document.createElement("div");
    subtitle.className = "node-shape";
    subtitle.textContent = item.subtitle || item.kind;
    heading.append(title);
    if (item.layerGroupId) {
      const layer = state.graph?.layer_groups.find((group) => group.layer_group_id === item.layerGroupId);
      const badge = document.createElement("div");
      badge.className = "node-layer";
      badge.textContent = layer?.qualified_name || item.layerGroupId;
      core.append(subtitle, badge);
    } else {
      core.append(subtitle);
    }
    if (item.kind === "semantic_stage") {
      const stats = document.createElement("div");
      stats.className = "stage-stats";
      const repeated = item.raw.template_instance_count
        ? `${item.raw.observed_block_count}/${item.raw.template_instance_count}` : item.raw.repeated_block_count;
      const values = [
        [item.raw.module_count, "modules"],
        [item.raw.operation_count, "operations"],
        [formatNumber(item.raw.parameter_count), "Trace params"],
        [repeated, "observed/template blocks"],
      ];
      for (const [value, label] of values) {
        const stat = document.createElement("span");
        stat.className = "stage-stat";
        const strong = document.createElement("strong");
        strong.textContent = String(value);
        stat.append(strong, ` ${label}`);
        stats.append(stat);
      }
      const tags = document.createElement("span");
      tags.className = "stage-tags";
      tags.textContent = item.raw.tags.join(" · ");
      stats.append(tags);
      core.append(stats);
    }
    if (state.mode !== "family") {
      const actions = document.createElement("div");
      actions.className = "node-actions";
      const itemModule = moduleById(item.raw.module_id);
      const commands = item.kind === "semantic_stage" ? [
        ["↗", "Open source modules", Boolean(itemModule), async () => {
          state.scopeModuleId = item.raw.module_id;
          await setMode("module");
        }],
        ["⊞", "Show underlying operations", Boolean(item.raw.operation_ids?.length), async () => {
          state.scopeModuleId = item.raw.module_id || state.graph.modules[0]?.module_id;
          await setMode("operation");
        }],
        [state.collapsedStages.has(item.id) ? "+" : "−", state.collapsedStages.has(item.id) ? "Expand stage card" : "Collapse stage card", true, async () => {
          if (state.collapsedStages.has(item.id)) state.collapsedStages.delete(item.id);
          else state.collapsedStages.add(item.id);
          await renderMode();
        }],
      ] : [
        ["↗", "Open module", Boolean(itemModule), async () => item.raw.module_id && selectModule(item.raw.module_id)],
        ["⊞", "Show operations", Boolean(itemModule), async () => {
          if (item.raw.module_id) state.scopeModuleId = item.raw.module_id;
          await setMode("operation");
        }],
        ["↑", "Go to parent module", Boolean(itemModule?.parent_module_id), async () => {
          const module = moduleById(item.raw.module_id);
          if (module?.parent_module_id) await selectModule(module.parent_module_id);
        }],
      ];
      for (const [label, titleText, enabled, action] of commands) {
        const button = document.createElement("button");
        button.className = "node-action";
        button.textContent = label;
        button.title = titleText;
        button.setAttribute("aria-label", titleText);
        button.disabled = !enabled;
        button.addEventListener("pointerdown", (event) => event.stopPropagation());
        button.addEventListener("click", async (event) => { event.stopPropagation(); await action(); });
        actions.append(button);
      }
      heading.append(actions);
    }
    heading.addEventListener("pointerdown", startNodeDrag);
    core.prepend(heading);
    const resizeHandle = document.createElement("button");
    resizeHandle.className = "node-resize-handle";
    resizeHandle.title = "Resize node";
    resizeHandle.setAttribute("aria-label", `Resize ${item.title}`);
    resizeHandle.addEventListener("pointerdown", startNodeResize);
    resizeHandle.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    const overview = document.createElement("div");
    overview.className = "overview-glyph";
    const overviewTitle = document.createElement("span");
    overviewTitle.className = "overview-title";
    overviewTitle.textContent = (item.title || item.kind).split(".").at(-1).slice(0, 24);
    const overviewIo = document.createElement("span");
    overviewIo.className = "overview-io";
    overviewIo.textContent = `${item.inputPorts.length}→${item.outputPorts.length}`;
    overview.append(overviewTitle, overviewIo);
    node.append(portBand(item, item.inputPorts, "input"), core, portBand(item, item.outputPorts, "output"), resizeHandle, overview);
    node.addEventListener("click", (event) => selectNode(item, event));
    node.addEventListener("dblclick", (event) => drillIntoNode(item, event));
    node.addEventListener("keydown", (event) => {
      if (event.target !== node) return;
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
  const tier = semanticZoomTier(state.zoom);
  const semanticFallback = state.mode === "architecture" && !state.semantic
    ? "Semantic guide not yet available; showing technical structure."
    : "";
  const graphStatus = tier === "overview"
    ? "Overview zoom — zoom in for node details"
    : (virtualized ? `${visible.size} / ${state.graphView.nodes.length} nodes visible` : "");
  showStatus([semanticFallback, graphStatus].filter(Boolean).join(" · "));
}

function portPoint(node, portId, direction) {
  const ports = direction === "output" ? node.outputPorts : node.inputPorts;
  const index = Math.max(0, ports.findIndex((port) => port.port_id === portId));
  const count = Math.max(1, ports.length);
  const position = positionFor(node.id);
  const size = sizeFor(node.id);
  return {
    x: position.x + size.width * ((index + 0.5) / count),
    y: position.y + (direction === "output" ? size.height : 0),
  };
}

function renderEdges(visible) {
  const byId = new Map(state.graphView.nodes.map((node) => [node.id, node]));
  const svg = $("#edges");
  const fragment = document.createDocumentFragment();
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  for (const confidence of ["exact", "lineage", "inferred", "ambiguous", "unresolved", "active"]) {
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", `edge-arrow-${confidence}`);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "9");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "5");
    marker.setAttribute("markerHeight", "5");
    marker.setAttribute("orient", "auto-start-reverse");
    const arrow = document.createElementNS("http://www.w3.org/2000/svg", "path");
    arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    arrow.setAttribute("class", `edge-arrow-shape ${confidence}`);
    marker.append(arrow);
    defs.append(marker);
  }
  fragment.append(defs);
  for (const edge of state.graphView.edges) {
    if (!visible.has(edge.source) || !visible.has(edge.target)) continue;
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) continue;
    const before = portPoint(source, edge.source_port, "output");
    const after = portPoint(target, edge.target_port, "input");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.classList.add("edge-path");
    const bend = Math.max(34, Math.abs(after.y - before.y) / 2);
    path.setAttribute("d", `M ${before.x} ${before.y} C ${before.x} ${before.y + bend}, ${after.x} ${after.y - bend}, ${after.x} ${after.y}`);
    path.dataset.confidence = edge.confidence || "exact";
    path.classList.toggle("active", state.pathEdges.has(edge.edge_id)
      || (!state.pathEdges.size && (edge.source === state.selectedId || edge.target === state.selectedId)));
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${edge.tensor_id || "route"} ${shapeLabel([{ shape: edge.shape }])} ${edge.confidence || "exact"}`;
    path.append(title);
    fragment.append(path);
  }
  svg.replaceChildren(fragment);
  renderContinuationMarkers(visible, byId);
}

function renderContinuationMarkers(visible, byId) {
  const container = $("#continuations");
  const viewport = $("#graph-viewport");
  const width = viewport.clientWidth;
  const height = viewport.clientHeight;
  const viewportRect = viewport.getBoundingClientRect();
  const renderedRectangles = new Map([...$("#nodes").querySelectorAll(".graph-node")].map((element) => {
    const visual = semanticZoomTier(state.zoom) === "overview"
      ? element.querySelector(".overview-glyph") || element
      : element;
    const rect = visual.getBoundingClientRect();
    return [element.dataset.id, {
      left: rect.left - viewportRect.left,
      top: rect.top - viewportRect.top,
      right: rect.right - viewportRect.left,
      bottom: rect.bottom - viewportRect.top,
      width: rect.width,
      height: rect.height,
      viewportWidth: width,
      viewportHeight: height,
    }];
  }));
  const screenRect = (node) => {
    if (renderedRectangles.has(node.id)) return renderedRectangles.get(node.id);
    const position = positionFor(node.id);
    const size = sizeFor(node.id);
    const left = state.pan.x + position.x * state.zoom;
    const top = state.pan.y + position.y * state.zoom;
    return {
      left, top,
      right: left + size.width * state.zoom,
      bottom: top + size.height * state.zoom,
      width: size.width * state.zoom,
      height: size.height * state.zoom,
      viewportWidth: width,
      viewportHeight: height,
    };
  };
  const rectangles = new Map([...byId].map(([id, node]) => [id, screenRect(node)]));
  const onscreen = new Set([...rectangles].filter(([, rect]) => (
    rect.right >= 0 && rect.left <= width && rect.bottom >= 0 && rect.top <= height
  )).map(([id]) => id));
  const groups = new Map();
  for (const edge of state.graphView.edges) {
    const sourceVisible = onscreen.has(edge.source);
    const targetVisible = onscreen.has(edge.target);
    if (sourceVisible === targetVisible) continue;
    const anchorId = sourceVisible ? edge.source : edge.target;
    const offscreenId = sourceVisible ? edge.target : edge.source;
    const direction = sourceVisible ? "to" : "from";
    const offscreenRect = rectangles.get(offscreenId);
    if (!offscreenRect) continue;
    const center = { x: (offscreenRect.left + offscreenRect.right) / 2, y: (offscreenRect.top + offscreenRect.bottom) / 2 };
    const overflow = {
      left: Math.max(0, -center.x),
      right: Math.max(0, center.x - width),
      top: Math.max(0, -center.y),
      bottom: Math.max(0, center.y - height),
    };
    const side = Object.entries(overflow).sort((left, right) => right[1] - left[1])[0][0];
    const anchor = byId.get(anchorId);
    const layer = anchor?.layerGroupId || byId.get(offscreenId)?.layerGroupId || "ungrouped";
    const key = `${side}:${direction}:${layer}`;
    if (!groups.has(key)) groups.set(key, {
      key, side, direction, layer, count: 0, anchorIds: new Set(), offscreenIds: new Set(), desiredValues: [],
    });
    const group = groups.get(key);
    group.count += 1;
    group.anchorIds.add(anchorId);
    group.offscreenIds.add(offscreenId);
    const anchorRect = rectangles.get(anchorId);
    group.desiredValues.push(side === "left" || side === "right"
      ? (anchorRect.top + anchorRect.bottom) / 2
      : (anchorRect.left + anchorRect.right) / 2);
  }
  const reservedRectangles = [
    ...graphOverlayRectangles(),
    ...[...rectangles.values()].filter((rect) => (
      rect.right >= 0 && rect.left <= width && rect.bottom >= 0 && rect.top <= height
    )),
  ];
  const placed = [];
  for (const side of ["left", "right", "top", "bottom"]) {
    const vertical = side === "left" || side === "right";
    const axisLength = vertical ? height : width;
    const markerSize = vertical ? 24 : 176;
    const stripSize = vertical ? 184 : 32;
    const items = [...groups.values()].filter((group) => group.side === side).map((group) => ({
      ...group,
      desired: group.desiredValues.reduce((sum, value) => sum + value, 0) / group.desiredValues.length,
    }));
    const reserved = intervalsForEdge(reservedRectangles, side, stripSize, axisLength);
    const result = placeMarkers1D(items, axisLength, markerSize, reserved, 8, 4);
    if (result.overflow.length && result.placements.length) {
      const last = result.placements.at(-1).item;
      last.collapsedCount = result.overflow.reduce((sum, item) => sum + item.count, 0);
      for (const item of result.overflow) for (const id of item.offscreenIds) last.offscreenIds.add(id);
    }
    placed.push(...result.placements.map((placement) => ({ ...placement, side })));
  }
  const fragment = document.createDocumentFragment();
  for (const { item: group, start, side } of placed) {
    const marker = document.createElement("button");
    marker.className = "continuation-marker";
    marker.dataset.side = side;
    marker.dataset.routeCount = String(group.count + (group.collapsedCount || 0));
    marker.dataset.targetId = [...group.offscreenIds][0] || "";
    const noun = group.direction === "to" ? "route" : "source";
    marker.textContent = group.collapsedCount
      ? `${group.direction} ${group.count} ${noun}${group.count === 1 ? "" : "s"} · ${group.collapsedCount} more`
      : `${group.direction} ${group.count} off-screen ${noun}${group.count === 1 ? "" : "s"}`;
    if (side === "left" || side === "right") {
      marker.style.left = `${side === "left" ? 4 : Math.max(4, width - 180)}px`;
      marker.style.top = `${start}px`;
    } else {
      marker.style.left = `${start}px`;
      marker.style.top = `${side === "top" ? 4 : Math.max(4, height - 28)}px`;
    }
    marker.addEventListener("click", (event) => {
      event.stopPropagation();
      const target = byId.get([...group.offscreenIds][0]);
      if (!target) return;
      const position = positionFor(target.id);
      const size = sizeFor(target.id);
      const safe = getGraphSafeRect();
      state.pan = {
        x: safe.left + safe.width / 2 - (position.x + size.width / 2) * state.zoom,
        y: safe.top + safe.height / 2 - (position.y + size.height / 2) * state.zoom,
      };
      updateTransform();
    });
    fragment.append(marker);
  }
  container.replaceChildren(fragment);
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
    const right = Math.max(...nodes.map((node) => positionFor(node.id).x + sizeFor(node.id).width)) + 18;
    const bottom = Math.max(...nodes.map((node) => positionFor(node.id).y + sizeFor(node.id).height)) + 18;
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
  const styles = getComputedStyle(document.documentElement);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = styles.getPropertyValue("--surface").trim();
  context.fillRect(0, 0, canvas.width, canvas.height);
  const scale = Math.min(canvas.width / state.bounds.width, canvas.height / state.bounds.height);
  for (const node of state.graphView.nodes) {
    context.fillStyle = state.graphMatches.has(node.id) ? "#356a9b"
      : state.pathNodes.has(node.id) ? "#a76508" : layerColor(node.layerGroupId);
    const position = positionFor(node.id);
    const size = sizeFor(node.id);
    context.fillRect(position.x * scale, position.y * scale, Math.max(3, size.width * scale), Math.max(2, Math.min(size.height, 10) * scale));
  }
  const viewport = $("#graph-viewport");
  context.strokeStyle = styles.getPropertyValue("--accent").trim();
  context.lineWidth = 3;
  context.strokeRect(
    Math.max(0, -state.pan.x / state.zoom) * scale,
    Math.max(0, -state.pan.y / state.zoom) * scale,
    Math.min(state.bounds.width, viewport.clientWidth / state.zoom) * scale,
    Math.min(state.bounds.height, viewport.clientHeight / state.zoom) * scale,
  );
}

function selectNode(item, event = {}, { sync = true, openOnMobile = true } = {}) {
  event.stopPropagation?.();
  if (event.ctrlKey || event.metaKey) {
    if (state.selectedIds.has(item.id)) state.selectedIds.delete(item.id);
    else state.selectedIds.add(item.id);
  } else {
    state.selectedIds.clear();
    state.selectedIds.add(item.id);
  }
  state.selectedId = item.id;
  const entity = semanticEntityFor(item.raw);
  state.selectedStageId = item.kind === "semantic_stage" ? item.id : entity?.stage_id || state.selectedStageId;
  state.selectedTag = item.raw.primary_tag || entity?.primary_tag || null;
  state.selectedPortId = null;
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
  if (state.pathMode) applyPathMode(state.pathMode, { render: false });
  updatePathControls();
  renderInspector(item.raw);
  renderVisibleGraph();
  renderBreadcrumbs();
  if (semanticZoomTier(state.zoom) === "overview" && !event.altKey) {
    setZoom(0.70);
    requestAnimationFrame(centerSelection);
  }
  persistViewState();
  if (sync) syncRoute();
  if (openOnMobile && window.innerWidth <= 980) openInspector();
}

function selectPort(item, port, direction, event) {
  event.stopPropagation();
  state.selectedId = item.id;
  state.selectedIds = new Set([item.id]);
  state.selectedPortId = port.port_id;
  const routeEdges = state.graphView.edges.filter((edge) => edge.tensor_id === port.tensor_id);
  const byId = new Map(state.graphView.nodes.map((node) => [node.id, node]));
  const producers = [...new Set(routeEdges.map((edge) => byId.get(edge.source)?.title).filter(Boolean))];
  const consumers = [...new Set(routeEdges.map((edge) => byId.get(edge.target)?.title).filter(Boolean))];
  const tensor = state.graph?.tensors?.find((value) => value.tensor_id === port.tensor_id) || {};
  state.inspected = {
    ...tensor,
    ...port,
    kind: "tensor_route",
    display_name: port.name || port.tensor_id,
    producer: producers.join(", ") || "external input",
    consumers: consumers.join(", ") || "external output",
    route: {
      producer: producers,
      consumers,
      confidence: [...new Set(routeEdges.map((edge) => edge.confidence || "exact"))],
      mutation: tensor.mutation_history || tensor.mutations || [],
      alias: port.alias_kind || tensor.alias_kind,
      required: port.required,
    },
    input_ports: direction === "input" ? [port] : [],
    output_ports: direction === "output" ? [port] : [],
  };
  state.pathMode = "isolate";
  state.pathEdges = new Set(routeEdges.map((edge) => edge.edge_id));
  state.pathNodes = new Set(routeEdges.flatMap((edge) => [edge.source, edge.target]));
  updatePathControls();
  renderInspector(state.inspected);
  renderVisibleGraph();
  if (window.innerWidth <= 980) openInspector();
}

function updatePathControls() {
  document.querySelectorAll(".path-control").forEach((button) => {
    button.disabled = !state.selectedId;
    button.classList.toggle("active", button.dataset.pathMode === state.pathMode);
  });
}

function applyPathMode(mode, { render = true } = {}) {
  if (!state.selectedId) return;
  state.pathMode = state.pathMode === mode && render ? null : mode;
  if (!state.pathMode) {
    state.pathNodes.clear();
    state.pathEdges.clear();
  } else {
    const path = tracePath(state.graphView.edges, state.selectedId, state.pathMode);
    state.pathNodes = path.nodes;
    state.pathEdges = path.edges;
  }
  updatePathControls();
  if (render) renderVisibleGraph();
}

function updateGraphSearch({ render = true } = {}) {
  state.graphQuery = $("#graph-search").value.trim().toLowerCase();
  state.graphMatches.clear();
  if (state.graphQuery) {
    for (const item of state.graphView.nodes) {
      const searchable = [
        item.title,
        item.subtitle,
        item.kind,
        item.raw.source_ref?.file,
        item.raw.source_ref?.symbol,
        ...item.inputPorts.flatMap((port) => [port.name, port.tensor_id, port.dtype, shapeLabel([port])]),
        ...item.outputPorts.flatMap((port) => [port.name, port.tensor_id, port.dtype, shapeLabel([port])]),
      ].filter(Boolean).join(" ").toLowerCase();
      if (searchable.includes(state.graphQuery)) state.graphMatches.add(item.id);
    }
  }
  if (render) renderVisibleGraph();
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
    "qualified_name", "module_path", "class_name", "block_type", "trace_confidence", "producer", "consumers",
    "tensor_id", "dtype", "alias_kind", "mutation_version", "required", "operation_count", "block_count",
  ];
  const rows = [];
  for (const key of preferred) if (value?.[key] !== undefined && value[key] !== null) rows.push([key.replaceAll("_", " "), value[key]]);
  if (value?.parameters !== undefined) {
    const count = typeof value.parameters === "number" ? value.parameters : value.parameters.total;
    if (Number.isFinite(count)) rows.push(["trace initialized parameters", count.toLocaleString()]);
  }
  const officialEstimate = value?.resource_preflight?.estimated_parameter_count;
  if (Number.isFinite(officialEstimate)) rows.push(["official parameter estimate", officialEstimate.toLocaleString()]);
  if (value?.input_ports) rows.push(["inputs", value.input_ports.length]);
  if (value?.output_ports) rows.push(["outputs", value.output_ports.length]);
  if (value?.layer_group_id) rows.push(["layer group", value.layer_group_id]);
  if (value?.sources) rows.push(["source assets", value.sources.length]);
  return rows;
}

function renderStructuralSummary() {
  const container = $("#structural-summary");
  if (!state.current) {
    container.replaceChildren();
    return;
  }
  const modules = state.graph?.modules || [];
  const depth = modules.length ? Math.max(...modules.map((module) => (
    module.qualified_name === "<root>" ? 0 : module.qualified_name.split(".").length
  ))) : "—";
  const templates = state.current.trace_templates || state.trace?.trace_templates || [];
  const repeated = templates.reduce((total, item) => total + Math.max(0, item.layer_indices.length - 1), 0);
  const inputs = state.graph?.nodes.find((node) => node.kind === "graph_input")?.output_ports || [];
  const outputs = state.current.top_level_outputs || [];
  const shapeFlow = `${shapeLabel(inputs) || "—"} → ${shapeLabel(outputs) || "—"}`;
  const total = state.current.parameters?.total || 0;
  const trainable = state.current.parameters?.trainable || 0;
  const metrics = [
    [depth, "Hierarchy depth"],
    [modules.length || "—", "Modules"],
    [repeated, "Repeated layers"],
    [`${formatNumber(trainable)} / ${formatNumber(total)}`, "Trace trainable / total"],
    [state.current.operation_count || state.current.trace_event_count || "—", "Operations"],
    [templates.length || state.graph?.layer_groups?.length || "—", "Layer structures"],
    [`${inputs.length} / ${outputs.length}`, "Inputs / outputs"],
    [shapeFlow, "Tensor shape flow"],
  ];
  const fragment = document.createDocumentFragment();
  for (const [value, label] of metrics) {
    const metric = document.createElement("div");
    metric.className = "summary-metric";
    const content = document.createElement("span");
    content.className = "summary-value";
    content.textContent = String(value);
    const name = document.createElement("span");
    name.className = "summary-label";
    name.textContent = label;
    metric.append(content, name);
    fragment.append(metric);
  }
  container.replaceChildren(fragment);
}

function renderSourceReference(value) {
  const reference = $("#source-reference");
  const ref = sourceRefFor(value);
  reference.replaceChildren();
  if (!ref?.file) {
    reference.textContent = state.current?.sources?.length
      ? "Select a module, operation, or source file"
      : "Source unavailable";
    reference.setAttribute("aria-label", reference.textContent);
    delete reference.dataset.tooltip;
    return null;
  }
  const lineNumber = ref.executed_line || ref.start_line;
  const basename = ref.file.split("/").at(-1);
  const full = `${ref.file}:${lineNumber} · ${ref.symbol || value?.target || "source"}`;
  const filePart = document.createElement("span");
  filePart.className = "source-basename";
  filePart.textContent = basename;
  const linePart = document.createElement("span");
  linePart.className = "source-line";
  linePart.textContent = `:${lineNumber}`;
  const symbol = document.createElement("span");
  symbol.className = "source-symbol";
  symbol.textContent = `· ${ref.symbol || value?.target || "source"}`;
  reference.append(filePart, linePart, symbol);
  reference.setAttribute("aria-label", `${full}. Activate to copy reference.`);
  reference.title = full;
  setTooltip(reference, full);
  reference.dataset.reference = full;
  return full;
}

function semanticRecordFor(value) {
  if (value?.stage_id && state.semantic?.stages?.some((stage) => stage.stage_id === value.stage_id)) {
    return state.semantic.stages.find((stage) => stage.stage_id === value.stage_id);
  }
  return semanticEntityFor(value);
}

function appendDistribution(container, titleText, items, total) {
  const section = document.createElement("section");
  section.className = "distribution-section";
  const title = document.createElement("h3");
  title.textContent = titleText;
  const bar = document.createElement("div");
  bar.className = "distribution-bar";
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", `${titleText}; total ${total.toLocaleString()}`);
  const legend = document.createElement("div");
  legend.className = "distribution-legend";
  items.forEach((item, index) => {
    const stage = state.semantic.stages.find((value) => value.stage_id === item.stage_id);
    const label = stage?.semantic_name || "Unclassified";
    const percent = total ? item.value / total * 100 : 0;
    const color = LAYER_COLORS[index % LAYER_COLORS.length];
    const segment = document.createElement("button");
    segment.className = "distribution-segment";
    segment.style.width = `${Math.max(item.value ? 1.5 : 0, percent)}%`;
    segment.style.setProperty("--segment-color", color);
    segment.setAttribute("aria-label", `${label}: ${item.value.toLocaleString()}, ${percent.toFixed(1)}%`);
    segment.disabled = !stage;
    segment.addEventListener("click", async () => {
      await setMode("architecture", { sync: false });
      const node = state.graphView.nodes.find((value) => value.id === item.stage_id);
      if (node) selectNode(node);
    });
    bar.append(segment);
    const entry = document.createElement("span");
    entry.style.setProperty("--segment-color", color);
    entry.textContent = `${label}: ${item.value.toLocaleString()} (${percent.toFixed(1)}%)`;
    legend.append(entry);
  });
  section.append(title, bar, legend);
  container.append(section);
}

function renderExplain(value) {
  const container = $("#explain-view");
  container.replaceChildren();
  const semantic = semanticRecordFor(value);
  if (!semantic) {
    const fallback = document.createElement("section");
    fallback.className = "explain-card";
    const heading = document.createElement("h3");
    heading.textContent = "Technical fallback";
    const text = document.createElement("p");
    text.textContent = "No semantic asset target is attached to this selection. Exact technical metadata remains available in Details.";
    fallback.append(heading, text);
    container.append(fallback);
    return;
  }
  const stage = semantic.stage_type ? semantic : state.semantic.stages.find((item) => item.stage_id === semantic.stage_id);
  const card = document.createElement("section");
  card.className = "explain-card";
  const heading = document.createElement("h3");
  heading.textContent = semantic.semantic_name;
  const description = document.createElement("p");
  description.textContent = semantic.what;
  const facts = document.createElement("dl");
  facts.className = "explain-facts";
  const journey = state.semantic.journeys?.[0];
  const inputRepresentations = journey?.steps.filter((step) => semantic.input_tensor_ids?.includes(step.tensor_id)).map((step) => step.representation) || [];
  const outputRepresentations = journey?.steps.filter((step) => semantic.output_tensor_ids?.includes(step.tensor_id)).map((step) => step.representation) || [];
  const rows = [
    ["Input representation", inputRepresentations.join(", ") || shapeLabel(semantic.input_shapes || []) || "Not observed"],
    ["Output representation", outputRepresentations.join(", ") || shapeLabel(semantic.output_shapes || []) || "Not observed"],
    ["Shape transform", `${shapeLabel(semantic.input_shapes || []) || "—"} → ${shapeLabel(semantic.output_shapes || []) || "—"}`],
    ["Graph position", semantic.graph_position ? `${semantic.graph_position.order + 1} of ${semantic.graph_position.total}` : `stage ${stage?.order + 1 || "—"}`],
    ["Exact class", semantic.source_class || "Stage aggregates exact sources below"],
    ["Exact path", semantic.qualified_name || semantic.source_name || stage?.module_ids?.map((id) => moduleById(id)?.qualified_name).filter(Boolean).join(", ") || "—"],
    ["Interface", semantic.interface_signature || "—"],
    ["Confidence", semantic.confidence],
    ["Provenance", semantic.provenance.join(" · ")],
  ];
  for (const [name, content] of rows) {
    const term = document.createElement("dt");
    term.textContent = name;
    const detail = document.createElement("dd");
    detail.textContent = String(content);
    facts.append(term, detail);
  }
  const tags = document.createElement("div");
  for (const tag of semantic.tags || []) {
    const badge = document.createElement("span");
    badge.className = "semantic-tag";
    badge.textContent = tag;
    tags.append(badge);
  }
  const confidence = document.createElement("span");
  confidence.className = `confidence-label ${semantic.confidence}`;
  confidence.textContent = semantic.confidence.replaceAll("_", " ");
  tags.append(confidence);
  card.append(heading, description, tags, facts);
  container.append(card);
  if (state.mode === "architecture") {
    const journeyFragment = document.createDocumentFragment();
    appendTensorJourney(journeyFragment, value);
    container.append(journeyFragment);
  }
  if (state.semantic?.metrics && (value?.stage_id || state.mode === "architecture")) {
    appendDistribution(container, `Trace parameters · mapped ${(state.semantic.coverage.parameter_stage_fraction * 100).toFixed(1)}%`, state.semantic.metrics.parameter_distribution, state.semantic.metrics.trace_parameter_total);
    appendDistribution(container, `Observed operations · mapped ${(state.semantic.coverage.operation_stage_fraction * 100).toFixed(1)}%`, state.semantic.metrics.operation_distribution, state.semantic.metrics.trace_operation_total);
  }
}

function renderInspector(value) {
  value ||= state.current || {};
  state.inspected = value;
  const semantic = semanticRecordFor(value);
  $("#inspector-title").textContent = state.labelMode === "source"
    ? (value.qualified_name || value.display_name || value.name || value.family_name || "Inspector")
    : (semantic?.semantic_name || value.display_name || value.qualified_name || value.name || value.family_name || "Inspector");
  const list = document.createElement("dl");
  for (const [name, content] of metadataRows(value)) {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = name;
    detail.textContent = String(content);
    list.append(term, detail);
  }
  $("#metadata").replaceChildren(list);
  const warnings = state.current?.warnings || [];
  const warning = $("#model-warning");
  warning.hidden = warnings.length === 0;
  warning.textContent = warnings.map((item) => item.message).join(" ");
  renderStructuralSummary();
  renderExplain(value);
  renderShapes(value);
  renderRuntime(value);
  renderSourceReference(value);
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

async function focusJourneyStep(step) {
  state.activeJourney = "primary-input-output";
  state.selectedStageId = step.stage_id;
  if (state.mode === "architecture") {
    const item = state.graphView.nodes.find((node) => node.id === step.stage_id);
    if (item) selectNode(item);
    return;
  }
  const item = state.graphView.nodes.find((node) => node.id === step.node_id);
  if (item) selectNode(item);
  else await selectOperation(step.node_id);
}

function appendTensorJourney(fragment, value) {
  const journey = state.semantic?.journeys?.[0];
  if (!journey) return;
  const selectedSemantic = semanticRecordFor(value);
  const selectedTensors = new Set([
    ...(selectedSemantic?.input_tensor_ids || []),
    ...(selectedSemantic?.output_tensor_ids || []),
  ]);
  const section = document.createElement("section");
  section.className = "journey";
  const title = document.createElement("h3");
  title.textContent = `Tensor Journey · ${journey.route_confidence} route`;
  const steps = document.createElement("div");
  steps.className = "journey-steps";
  journey.steps.forEach((step) => {
    const button = document.createElement("button");
    button.className = "journey-step";
    if (selectedTensors.has(step.tensor_id)) button.classList.add("active");
    button.setAttribute("aria-label", `${step.representation}, shape ${step.shape.join(" by ")}, ${step.transform}, ${step.route_confidence} route`);
    const representation = document.createElement("span");
    representation.className = "journey-representation";
    representation.textContent = step.representation;
    const shape = document.createElement("span");
    shape.className = "journey-shape";
    shape.textContent = `[${step.shape.join(", ")}]`;
    const transform = document.createElement("span");
    transform.className = "journey-meta";
    transform.textContent = `${step.transform} · ${step.dtype} · ${step.route_confidence}`;
    const explanation = document.createElement("span");
    explanation.className = "journey-meta";
    explanation.textContent = step.explanation;
    button.append(representation, shape, transform, explanation);
    button.addEventListener("click", () => focusJourneyStep(step));
    steps.append(button);
  });
  section.append(title, steps);
  fragment.append(section);
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
  appendTensorJourney(fragment, value);
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
  if (value?.route) appendRuntimeSection(container, "Tensor route", Object.entries(value.route));
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
    renderSourceReference(value);
    lines.replaceChildren();
    repository.hidden = true;
    return;
  }
  renderSourceReference(value);
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
    if (traceLine?.variables?.length) {
      const variableLabel = document.createElement("div");
      const sorted = [...traceLine.variables].sort((left, right) => (left.name || "").localeCompare(right.name || ""));
      const compact = sorted.slice(0, 3);
      const names = compact.map((item) => `${item.name || "value"}:${item.tensor_shape?.join(",") || "?"}`).join(", ");
      variableLabel.className = "line-variables";
      variableLabel.textContent = compact.length < traceLine.variables.length
        ? `${names}, +${traceLine.variables.length - compact.length} more`
        : names;
      row.title = `line vars: ${traceLine.variables.map((item) => item.name).join(", ")}`;
      code.append(variableLabel);
      code.append(document.createTextNode("\n"));
    }
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
  document.querySelectorAll(".inspector-tab").forEach((tab) => {
    const active = tab.dataset.panel === panel;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll(".inspector-panel").forEach((section) => section.classList.toggle("active", section.id === `${panel}-panel`));
  if (panel === "source") await renderSource(state.inspected);
  if (panel === "config" && state.current) await renderConfigPanel();
}

function handleTablistKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]:not([disabled])')];
  const current = tabs.indexOf(document.activeElement);
  if (current < 0) return;
  event.preventDefault();
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
    : event.key === "ArrowRight" ? (current + 1) % tabs.length : (current - 1 + tabs.length) % tabs.length;
  tabs[next].focus();
  tabs[next].click();
}

function appendConfigRow(fragment, key, value, changed = false) {
  const row = document.createElement("div");
  row.className = `config-row${changed ? " changed" : ""}`;
  const name = document.createElement("span");
  name.className = "config-key";
  name.textContent = key;
  const content = document.createElement("span");
  content.className = "config-value";
  content.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  row.append(name, content);
  fragment.append(row);
}

async function renderConfigPanel() {
  const view = $("#config-view");
  view.textContent = "Loading config...";
  document.querySelectorAll(".config-mode").forEach((button) => {
    button.classList.toggle("active", button.dataset.configMode === state.configMode);
  });
  const link = $("#official-config-link");
  link.hidden = !state.current?.official_config_source?.pinned_url;
  if (!link.hidden) link.href = state.current.official_config_source.pinned_url;
  try {
    const fragment = document.createDocumentFragment();
    if (state.configMode === "official") {
      state.officialConfig ??= await store.officialConfig(state.current);
      if (!state.officialConfig) {
        view.textContent = state.current.warnings?.[0]?.message || "Official config unavailable.";
        return;
      }
      const source = state.current.official_config_source;
      const provenance = document.createElement("div");
      provenance.className = "config-provenance";
      provenance.textContent = `${source.repo_id} @ ${source.revision.slice(0, 12)} · ${source.license} · sha256:${source.sha256.slice(0, 12)}`;
      fragment.append(provenance);
      for (const [key, value] of [...flattenConfig(state.officialConfig)].slice(0, 2000)) appendConfigRow(fragment, key, value);
    } else if (state.configMode === "trace") {
      state.traceConfig ??= await store.traceConfig(state.current);
      const config = state.traceConfig.config || state.traceConfig;
      for (const [key, value] of [...flattenConfig(config)].slice(0, 2000)) appendConfigRow(fragment, key, value);
    } else {
      state.configDiff ??= await store.configDiff(state.current);
      if (!state.configDiff) {
        view.textContent = "Differences unavailable because the official config could not be fetched.";
        return;
      }
      for (const item of state.configDiff.differences) {
        appendConfigRow(fragment, `${item.path} · ${item.status}`, {
          official: item.official_value,
          trace: item.trace_value,
        }, true);
      }
    }
    view.replaceChildren(fragment);
  } catch (error) {
    view.textContent = error.message;
  }
}

function updateDensityButton() {
  const button = $("#density-button");
  button.classList.toggle("active", state.mode === "operation");
  button.textContent = state.mode === "operation" ? "⊟" : "⊞";
  button.title = state.mode === "operation" ? "Collapse to module topology" : "Expand operation topology";
  button.disabled = state.mode === "family" || state.mode === "blocks";
}

async function toggleDensity() {
  if (state.mode === "family") return;
  await setMode(state.mode === "operation" ? "module" : "operation");
}

function updateTransform() {
  $("#graph-canvas").style.transform = `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
  $("#zoom-value").value = `${Math.round(state.zoom * 100)}%`;
  const viewport = $("#graph-viewport");
  viewport.dataset.zoomTier = semanticZoomTier(state.zoom);
  viewport.dataset.zoomLevel = state.zoom < 0.55 ? "low" : state.zoom < 0.95 ? "medium" : "high";
  viewport.style.setProperty("--graph-zoom", state.zoom);
  viewport.style.setProperty("--inverse-zoom", 1 / state.zoom);
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
  const safe = getGraphSafeRect();
  state.bounds = graphBounds(state.graphView.nodes, allPositions(), allSizes());
  state.zoom = Math.min(1.1, Math.max(0.16, Math.min(safe.width / state.bounds.width, safe.height / state.bounds.height) * 0.9));
  state.pan = {
    x: safe.left + Math.max(0, (safe.width - state.bounds.width * state.zoom) / 2),
    y: safe.top + Math.max(0, (safe.height - state.bounds.height * state.zoom) / 2),
  };
  updateTransform();
}

function centerSelection() {
  if (!state.selectedId) return;
  const position = positionFor(state.selectedId);
  const size = sizeFor(state.selectedId);
  const safe = getGraphSafeRect();
  state.pan = {
    x: safe.left + safe.width / 2 - (position.x + size.width / 2) * state.zoom,
    y: safe.top + safe.height / 2 - (position.y + size.height / 2) * state.zoom,
  };
  updateTransform();
}

function resetLayout() {
  localStorage.removeItem(positionStorageKey());
  state.userPositions = new Map();
  state.userSizes = new Map();
  state.pan = { x: 24, y: 24 };
  state.zoom = 1;
  renderMode({ fit: true });
}

function startNodeDrag(event) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const handle = event.currentTarget;
  const node = handle.closest(".graph-node");
  const id = node.dataset.id;
  const start = { x: event.clientX, y: event.clientY };
  const initial = { ...positionFor(id) };
  let moved = false;
  handle.setPointerCapture(event.pointerId);
  node.classList.add("dragging");
  const move = (next) => {
    if (next.pointerId !== event.pointerId) return;
    next.preventDefault();
    const position = {
      x: Math.max(0, initial.x + (next.clientX - start.x) / state.zoom),
      y: Math.max(0, initial.y + (next.clientY - start.y) / state.zoom),
    };
    moved ||= Math.abs(next.clientX - start.x) > 3 || Math.abs(next.clientY - start.y) > 3;
    state.userPositions.set(id, position);
    node.style.left = `${position.x}px`;
    node.style.top = `${position.y}px`;
    scheduleGeometryRender();
  };
  const end = (next) => {
    if (next.pointerId !== event.pointerId) return;
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    node.classList.remove("dragging");
    if (moved) {
      handle.addEventListener("click", (clickEvent) => {
        clickEvent.preventDefault();
        clickEvent.stopPropagation();
      }, { capture: true, once: true });
    }
    saveUserPositions();
    scheduleGeometryRender();
  };
  window.addEventListener("pointermove", move, { passive: false });
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
}

function startNodeResize(event) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const handle = event.currentTarget;
  const node = handle.closest(".graph-node");
  const id = node.dataset.id;
  const start = { x: event.clientX, y: event.clientY };
  const initial = { ...sizeFor(id) };
  handle.setPointerCapture(event.pointerId);
  node.classList.add("resizing");
  const move = (next) => {
    if (next.pointerId !== event.pointerId) return;
    next.preventDefault();
    const size = {
      width: Math.min(MAX_NODE_WIDTH, Math.max(MIN_NODE_WIDTH, initial.width + (next.clientX - start.x) / state.zoom)),
      height: Math.min(
        MAX_NODE_HEIGHT,
        Math.max(
          node.dataset.kind === "semantic_stage" ? STAGE_NODE_HEIGHT : MIN_NODE_HEIGHT,
          initial.height + (next.clientY - start.y) / state.zoom,
        ),
      ),
    };
    state.userSizes.set(id, size);
    node.style.width = `${size.width}px`;
    node.style.height = `${size.height}px`;
    scheduleGeometryRender();
  };
  const end = (next) => {
    if (next.pointerId !== event.pointerId) return;
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    node.classList.remove("resizing");
    saveUserPositions();
    scheduleGeometryRender();
  };
  window.addEventListener("pointermove", move, { passive: false });
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
}

function viewportInteractiveTarget(target) {
  return target instanceof Element && target.closest([
    "button", "a", "input", "select", "textarea", "summary", "label",
    "[contenteditable='true']", "[role='button']", "[role='link']",
    "[role='checkbox']", "[role='tab']", ".graph-legend", ".minimap-panel",
    ".continuation-marker",
  ].join(", "));
}

function beginViewportGesture(event) {
  if (viewportInteractiveTarget(event.target) || event.button !== 0) return;
  event.preventDefault();
  window.getSelection()?.removeAllRanges();
  const viewport = $("#graph-viewport");
  state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  viewport.setPointerCapture(event.pointerId);
  state.viewportDrag = {
    started: false,
    startX: event.clientX,
    startY: event.clientY,
  };
  if (state.pointers.size === 1) {
    state.gesture = { type: "pan", x: event.clientX, y: event.clientY, pan: { ...state.pan } };
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
    updateTransform();
  } else if (state.gesture?.type === "pan") {
    const moved = Math.abs(event.clientX - state.viewportDrag.startX) + Math.abs(event.clientY - state.viewportDrag.startY);
    if (!state.viewportDrag.started && moved < VIEWPORT_PAN_DRAG_THRESHOLD) return;
    if (!state.viewportDrag.started) {
      state.viewportDrag.started = true;
      $("#graph-viewport").classList.add("panning");
      event.preventDefault();
      window.getSelection()?.removeAllRanges();
    }
    state.pan = {
      x: state.gesture.pan.x + event.clientX - state.gesture.x,
      y: state.gesture.pan.y + event.clientY - state.gesture.y,
    };
    event.preventDefault();
    updateTransform();
  }
}

function endViewportGesture(event) {
  state.pointers.delete(event.pointerId);
  if (state.pointers.size === 0) state.viewportDrag = { started: false, startX: 0, startY: 0 };
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

function compareStageLabel(stage) {
  if (!stage) return "—";
  if (state.labelMode === "source") return stage.stage_type;
  if (state.labelMode === "both") return `${stage.semantic_name} · ${stage.stage_type}`;
  return stage.semantic_name;
}

function semanticTargetButton(version, semantic, stage, label) {
  if (!stage) return document.createTextNode("—");
  const button = document.createElement("button");
  button.textContent = label;
  button.addEventListener("click", async () => {
    closeCompare();
    await loadVersion(version.version_id, { sync: false });
    await setMode("architecture", { sync: false });
    const item = state.graphView.nodes.find((node) => node.id === stage.stage_id);
    if (item) selectNode(item);
  });
  return button;
}

function appendSemanticTable(container, titleText, rows, left, right, leftSemantic, rightSemantic) {
  const title = document.createElement("h3");
  title.className = "compare-section-title";
  title.textContent = titleText;
  const table = document.createElement("table");
  table.className = "compare-table";
  const head = document.createElement("thead");
  const heading = document.createElement("tr");
  ["Shared category", left.family_name, right.family_name, "Relationship"].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    heading.append(cell);
  });
  head.append(heading);
  const body = document.createElement("tbody");
  rows.forEach((rowValue) => {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    label.textContent = rowValue.label;
    const leftCell = document.createElement("td");
    leftCell.append(semanticTargetButton(left, leftSemantic, rowValue.leftStage, rowValue.leftText || compareStageLabel(rowValue.leftStage)));
    if (rowValue.leftTooltip) setTooltip(leftCell.querySelector("button"), rowValue.leftTooltip);
    const rightCell = document.createElement("td");
    rightCell.append(semanticTargetButton(right, rightSemantic, rowValue.rightStage, rowValue.rightText || compareStageLabel(rowValue.rightStage)));
    if (rowValue.rightTooltip) setTooltip(rightCell.querySelector("button"), rowValue.rightTooltip);
    const relationship = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "relationship-badge";
    badge.textContent = rowValue.relationship;
    relationship.append(badge);
    row.append(label, leftCell, rightCell, relationship);
    body.append(row);
  });
  table.append(head, body);
  container.append(title, table);
}

async function openCompare({ sync = true, view = "architecture" } = {}) {
  const content = $("#compare-content");
  content.replaceChildren();
  $("#compare-pane").hidden = false;
  updateScrim();
  if (state.compareIds.length < 2) {
    content.textContent = "Select two models in the catalog to compare.";
    return;
  }
  if (sync) {
    const segments = ["compare", ...state.compareIds, "view", view, "detail", state.detailMode, "labels", state.labelMode];
    history.pushState(null, "", `${location.pathname}${location.search}#/${segments.map(encodeURIComponent).join("/")}`);
    $("#uri-input").value = `modelvis:/compare/${state.compareIds.map(encodeURIComponent).join("/")}/view/${view}`;
  }
  try {
    const [left, right] = await Promise.all(state.compareIds.map((id) => store.version(id)));
    const [leftConfig, rightConfig, leftTrace, rightTrace, leftSemantic, rightSemantic] = await Promise.all([
      store.config(left), store.config(right), store.trace(left), store.trace(right), store.semantic(left), store.semantic(right),
    ]);
    const configDifferenceCount = configDifferences(leftConfig, rightConfig).length;
    appendCompareTable(content, [
      ["Version", left.version_id, right.version_id],
      ["Domain", leftSemantic.domain, rightSemantic.domain],
      ["Task", leftSemantic.task, rightSemantic.task],
      ["Library", left.library, right.library],
      ["Trace initialized parameters", left.parameters.total, right.parameters.total],
      ["Official parameter estimate", leftSemantic.metrics.official_parameter_estimate ?? "—", rightSemantic.metrics.official_parameter_estimate ?? "—"],
      ["Observed operations", left.operation_count, right.operation_count],
      ["Source files", sourceFiles(leftTrace).length, sourceFiles(rightTrace).length],
      ["Config fields changed", "—", "—", configDifferenceCount],
      ["Primary journey", leftSemantic.journeys[0]?.steps.map((step) => `${step.representation} ${JSON.stringify(step.shape)}`).join(" → ") || "—", rightSemantic.journeys[0]?.steps.map((step) => `${step.representation} ${JSON.stringify(step.shape)}`).join(" → ") || "—", "Trace facts"],
    ], left.family_name, right.family_name);

    const stageTypes = [...new Set([...leftSemantic.stages, ...rightSemantic.stages].map((stage) => stage.stage_type))];
    appendSemanticTable(content, "Semantic stage presence and order", stageTypes.map((stageType) => {
      const leftStage = leftSemantic.stages.find((stage) => stage.stage_type === stageType);
      const rightStage = rightSemantic.stages.find((stage) => stage.stage_type === stageType);
      return {
        label: stageType,
        leftStage,
        rightStage,
        leftText: leftStage ? `${compareStageLabel(leftStage)} · order ${leftStage.order + 1}` : "—",
        rightText: rightStage ? `${compareStageLabel(rightStage)} · order ${rightStage.order + 1}` : "—",
        relationship: leftStage && rightStage ? "Same stage type" : leftStage ? `Only in ${left.family_name}` : `Only in ${right.family_name}`,
      };
    }), left, right, leftSemantic, rightSemantic);

    const tagIds = ["input", "embedding_or_projection", "position_or_context", "attention_or_mixer", "feed_forward", "normalization_or_residual", "aggregation_or_decoder", "output_or_head", "other"];
    appendSemanticTable(content, "Exact class/interface tags", tagIds.map((tag) => {
      const leftEntities = Object.values(leftSemantic.entities).filter((entity) => entity.tags.includes(tag) && entity.entity_kind === "module");
      const rightEntities = Object.values(rightSemantic.entities).filter((entity) => entity.tags.includes(tag) && entity.entity_kind === "module");
      const leftStage = leftSemantic.stages.find((stage) => stage.stage_id === leftEntities[0]?.stage_id);
      const rightStage = rightSemantic.stages.find((stage) => stage.stage_id === rightEntities[0]?.stage_id);
      const identities = (entities) => [...new Set(entities.map((entity) => `${entity.source_class} · ${entity.interface_signature}`).filter(Boolean))];
      const leftIdentities = identities(leftEntities);
      const rightIdentities = identities(rightEntities);
      return {
        label: tag,
        leftStage,
        rightStage,
        leftText: leftIdentities.length ? leftIdentities.slice(0, 3).join("; ") : "—",
        rightText: rightIdentities.length ? rightIdentities.slice(0, 3).join("; ") : "—",
        leftTooltip: leftIdentities.join("\n"),
        rightTooltip: rightIdentities.join("\n"),
        relationship: leftEntities.length && rightEntities.length ? "Same tag" : leftEntities.length ? `Only in ${left.family_name}` : rightEntities.length ? `Only in ${right.family_name}` : "Absent in both",
      };
    }), left, right, leftSemantic, rightSemantic);

    const distributionRows = stageTypes.map((stageType) => {
      const leftStage = leftSemantic.stages.find((stage) => stage.stage_type === stageType);
      const rightStage = rightSemantic.stages.find((stage) => stage.stage_type === stageType);
      const summary = (stage, metrics) => stage
        ? `${stage.parameter_count.toLocaleString()} params · ${stage.operation_count.toLocaleString()} ops · ${stage.observed_block_count}/${stage.template_instance_count} observed/template blocks`
        : "—";
      return {
        label: stageType,
        leftStage,
        rightStage,
        leftText: summary(leftStage, leftSemantic.metrics),
        rightText: summary(rightStage, rightSemantic.metrics),
        relationship: leftStage && rightStage ? "Comparable trace distributions" : leftStage ? `Only in ${left.family_name}` : `Only in ${right.family_name}`,
      };
    });
    appendSemanticTable(content, "Stage parameter and operation distributions", distributionRows, left, right, leftSemantic, rightSemantic);
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
    else if (location.hash.includes("/compare/")) await applyRoute(location.hash);
    else if (index.length) {
      const saved = savedViewState();
      const versionId = state.index.some((item) => item.version_id === saved.versionId) ? saved.versionId : index[0].version_id;
      const primaryView = ["architecture", "family", "module", "blocks", "operation"].includes(saved.primaryView) ? saved.primaryView : "architecture";
      await loadVersion(versionId, { sync: false });
      await setMode(primaryView, { sync: false });
      await switchInspectorPanel(state.detailMode === "beginner" ? "explain" : "details");
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
$("#graph-search").addEventListener("input", () => updateGraphSearch());
document.querySelectorAll(".path-control").forEach((button) => button.addEventListener("click", () => applyPathMode(button.dataset.pathMode)));
document.querySelectorAll(".navigator-tab").forEach((button) => button.addEventListener("click", () => switchNavigator(button.dataset.navigator)));
document.querySelectorAll(".mode").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
document.querySelectorAll(".inspector-tab").forEach((button) => button.addEventListener("click", () => switchInspectorPanel(button.dataset.panel)));
document.querySelectorAll('[role="tablist"]').forEach((tablist) => tablist.addEventListener("keydown", handleTablistKeydown));
$("#detail-mode").addEventListener("change", (event) => setDetailMode(event.target.value));
$("#label-mode").addEventListener("change", (event) => setLabelMode(event.target.value));
document.querySelectorAll(".config-mode").forEach((button) => button.addEventListener("click", async () => {
  state.configMode = button.dataset.configMode;
  await renderConfigPanel();
}));
$("#uri-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await applyRoute($("#uri-input").value); } catch (error) { showStatus(error.message); }
});
$("#copy-source").addEventListener("click", async () => copyText(await selectedSourceCode(), "Source code"));
$("#source-reference").addEventListener("click", () => copyText($("#source-reference").dataset.reference || "", "Source reference"));
$("#zoom-in").addEventListener("click", () => setZoom(state.zoom + 0.12));
$("#zoom-out").addEventListener("click", () => setZoom(state.zoom - 0.12));
$("#fit-button").addEventListener("click", fitGraph);
$("#reset-button").addEventListener("click", resetLayout);
$("#legend-toggle").addEventListener("click", () => {
  state.overlayState.legend = !state.overlayState.legend;
  applyOverlayState();
});
$("#minimap-toggle").addEventListener("click", () => {
  state.overlayState.minimap = !state.overlayState.minimap;
  applyOverlayState();
});
$("#theme-button").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
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
  if (viewportInteractiveTarget(event.target)) return;
  state.selectedId = null;
  state.selectedStageId = null;
  state.selectedCallId = null;
  state.selectedIds.clear();
  renderVisibleGraph();
  persistViewState();
  syncRoute();
});
$("#minimap").addEventListener("click", (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  const worldX = (event.clientX - rect.left) / rect.width * state.bounds.width;
  const worldY = (event.clientY - rect.top) / rect.height * state.bounds.height;
  const safe = getGraphSafeRect();
  state.pan = {
    x: safe.left + safe.width / 2 - worldX * state.zoom,
    y: safe.top + safe.height / 2 - worldY * state.zoom,
  };
  updateTransform();
});
window.addEventListener("hashchange", () => applyRoute(location.hash).catch((error) => showStatus(error.message)));
window.addEventListener("resize", scheduleVisibleRender);
document.addEventListener("mouseover", (event) => showTooltip(event.target.closest?.("[data-tooltip]")));
document.addEventListener("mouseout", (event) => {
  if (!event.relatedTarget?.closest?.("[data-tooltip]")) hideTooltip();
});
document.addEventListener("focusin", (event) => showTooltip(event.target.closest?.("[data-tooltip]")));
document.addEventListener("focusout", (event) => {
  if (!event.relatedTarget?.closest?.("[data-tooltip]")) hideTooltip();
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closeSidebar(); closeInspector(); closeCompare(); }
  if (event.key === "0" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); fitGraph(); }
  const target = event.target;
  const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement || target?.isContentEditable;
  const value = selectedGraphValue();
  if (typing) return;
  const key = event.key.toLowerCase();
  const isSystemShortcut = event.ctrlKey || event.metaKey;
  const isLegacyShortcut = event.altKey && event.shiftKey;
  if (!isSystemShortcut && !isLegacyShortcut) return;

  if ((isSystemShortcut && key === "w") || (isLegacyShortcut && key === "m")) {
    event.preventDefault();
    copyText(value?.display_name || value?.name || value?.qualified_name || "", "Module name");
  }
  if ((isSystemShortcut && key === "q") || (isLegacyShortcut && key === "p")) {
    event.preventDefault();
    copyText(value?.qualified_name || value?.module_path || "", "Module path");
  }
  if ((isSystemShortcut && key === "e") || (isLegacyShortcut && key === "s")) {
    event.preventDefault();
    selectedSourceCode().then((text) => copyText(text, "Source code"));
  }
});

initializeViewPreferences();
initializeTheme();
initializeOverlayState();
start();
