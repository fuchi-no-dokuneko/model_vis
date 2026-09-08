const element = (name) => document.createElementNS("http://www.w3.org/2000/svg", name);

export function overviewEdges(layout, state) {
  const fragment = document.createDocumentFragment(), defs = element("defs");
  for (const confidence of ["exact", "lineage", "inferred", "ambiguous", "unresolved", "active"]) {
    const marker = element("marker"), shape = element("path");
    for (const [key, value] of Object.entries({ id: `edge-arrow-${confidence}`, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse" })) marker.setAttribute(key, value);
    shape.setAttribute("d", "M 0 0 L 10 5 L 0 10 z"); shape.setAttribute("class", `edge-arrow-shape ${confidence}`);
    marker.append(shape); defs.append(marker);
  }
  fragment.append(defs);
  for (const edge of layout.edges) {
    const a = layout.placements[edge.source], b = layout.placements[edge.target];
    const x1 = (a.x + 50 - state.pan.x) / state.zoom, y1 = (a.y + 44 - state.pan.y) / state.zoom;
    const x2 = (b.x + 50 - state.pan.x) / state.zoom, y2 = (b.y - state.pan.y) / state.zoom;
    const path = element("path"), title = element("title");
    path.setAttribute("class", "edge-path"); path.dataset.confidence = edge.confidence;
    path.style.vectorEffect = "none";
    path.style.strokeWidth = `${1.5 / state.zoom}px`;
    const dash = { inferred: [5, 4], ambiguous: [8, 3, 2, 3], unresolved: [2, 5] }[edge.confidence];
    if (dash) path.style.strokeDasharray = dash.map((value) => value / state.zoom).join(" ");
    path.setAttribute("d", `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`);
    title.textContent = `${edge.tensorIds.length} observed tensor routes between groups · ${edge.confidence}`;
    path.append(title); fragment.append(path);
  }
  document.querySelector("#edges").replaceChildren(fragment);
}
