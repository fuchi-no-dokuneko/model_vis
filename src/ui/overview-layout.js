export function overviewLayout(view, semantic, safe) {
  const columns = Math.max(1, Math.floor(safe.width / 112));
  const rows = Math.max(1, Math.floor(safe.height / 58));
  const capacity = columns * rows;
  let groups;
  if (view.nodes.length <= capacity) groups = view.nodes.map((item) => [item]);
  else {
    const stages = new Map();
    for (const item of view.nodes) {
      const key = semantic?.entities?.[item.id]?.stage_id || item.layerGroupId || item.kind;
      if (!stages.has(key)) stages.set(key, []);
      stages.get(key).push(item);
    }
    groups = [...stages.values()];
    if (groups.length > capacity) {
      const size = Math.ceil(groups.length / capacity), compact = [];
      for (let i = 0; i < groups.length; i += size) compact.push(groups.slice(i, i + size).flat());
      groups = compact;
    }
  }
  const usedColumns = Math.min(columns, groups.length);
  const usedRows = Math.ceil(groups.length / usedColumns);
  const placements = groups.map((items, index) => ({
    items,
    x: safe.left + (index % usedColumns + 0.5) * safe.width / usedColumns - 50,
    y: safe.top + (Math.floor(index / usedColumns) + 0.5) * safe.height / usedRows - 22,
  }));
  const owners = new Map();
  placements.forEach((group, index) => group.items.forEach((item) => owners.set(item.id, index)));
  const edges = new Map();
  for (const edge of view.edges) {
    const source = owners.get(edge.source), target = owners.get(edge.target);
    if (source == null || target == null || source === target) continue;
    const key = `${source}:${target}:${edge.confidence}`;
    if (!edges.has(key)) edges.set(key, { source, target, confidence: edge.confidence || "exact", tensorIds: [] });
    edges.get(key).tensorIds.push(edge.tensor_id);
  }
  return { placements, edges: [...edges.values()] };
}
