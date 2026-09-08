import { overviewLayout } from "./overview-layout.js";
import { overviewEdges } from "./overview-edges.js";

export function renderOverview(state, safe, select) {
  const layout = overviewLayout(state.graphView, state.semantic, safe);
  const fragment = document.createDocumentFragment();
  for (const group of layout.placements) {
    const item = group.items.find((entry) => state.graphMatches.has(entry.id)) || group.items[0];
    const node = document.createElement("article");
    node.className = "graph-node overview-group";
    node.dataset.id = item.id; node.dataset.kind = item.kind;
    node.dataset.groupSize = group.items.length;
    node.style.left = `${(group.x - state.pan.x) / state.zoom}px`;
    node.style.top = `${(group.y - state.pan.y) / state.zoom}px`;
    node.style.width = `${100 / state.zoom}px`; node.style.height = `${44 / state.zoom}px`;
    node.tabIndex = 0; node.setAttribute("role", "button");
    for (const [className, ids] of [["search-match", state.graphMatches], ["multi-selected", state.selectedIds], ["path-active", state.pathNodes]]) node.classList.toggle(className, group.items.some((entry) => ids.has(entry.id)));
    node.classList.toggle("selected", group.items.some((entry) => entry.id === state.selectedId));
    const glyph = document.createElement("div"); glyph.className = "overview-glyph";
    const title = document.createElement("span"); title.className = "overview-title"; title.textContent = item.title;
    const count = document.createElement("span"); count.className = "overview-io"; count.textContent = group.items.length === 1 ? `${item.inputPorts.length}→${item.outputPorts.length}` : `${group.items.length} nodes`;
    const label = group.items.length === 1 ? item.title : `Expand group of ${group.items.length} nodes near ${item.title}`;
    node.setAttribute("aria-label", label); node.title = `${label}\n${group.items.slice(0, 12).map((entry) => entry.title).join("\n")}`;
    glyph.append(title, count); node.append(glyph);
    node.addEventListener("click", (event) => select(item, event));
    node.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); select(item, event); } });
    fragment.append(node);
  }
  document.querySelector("#nodes").replaceChildren(fragment);
  overviewEdges(layout, state);
  document.querySelector("#continuations").replaceChildren();
  document.querySelector("#layer-groups").replaceChildren();
  return layout.placements.length;
}
