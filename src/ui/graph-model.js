function shapeText(records = []) {
  return records.map((record) => record.shape || record).filter((shape) => Array.isArray(shape))
    .map((shape) => `[${shape.join(", ")}]`).join(" ");
}

function sequentialEdges(nodes) {
  return nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id }));
}

function operationNode(operation) {
  return {
    id: operation.op_id,
    title: operation.display_name,
    subtitle: shapeText(operation.outputs) || operation.kind,
    kind: operation.kind,
    depth: 0,
    raw: operation,
  };
}

export function projectGraph({ mode, current, family, index, graph, blocks, trace, expanded, activeBlock }) {
  if (!current) return { nodes: [], edges: [] };
  if (mode === "family") {
    const root = {
      id: `family:${current.family_id}`,
      title: current.family_name,
      subtitle: `${family?.versions.length || 1} version${family?.versions.length === 1 ? "" : "s"}`,
      kind: "family",
      depth: 0,
      raw: current,
    };
    const versions = (family?.versions || [current.version_id]).map((versionId) => {
      const summary = index.find((item) => item.version_id === versionId) || current;
      return {
        id: `version:${versionId}`,
        title: summary.family_name || current.family_name,
        subtitle: `${Number(summary.parameters || current.parameters.total).toLocaleString()} parameters`,
        kind: "version",
        depth: 1,
        raw: summary,
      };
    });
    return { nodes: [root, ...versions], edges: versions.map((node) => ({ source: root.id, target: node.id })) };
  }
  if (mode === "version" && graph) {
    const moduleNodes = graph.nodes.filter((node) => node.kind === "ModuleNode" && node.name !== "module-node");
    const collapsedNodes = moduleNodes.length
      ? moduleNodes
      : graph.nodes.filter((node) => node.kind === "FunctionNode");
    const sourceNodes = expanded ? graph.nodes : collapsedNodes;
    const nodes = sourceNodes.map((node) => ({
      id: node.id,
      title: node.name === "module-node" ? current.entrypoint_class : node.name,
      subtitle: shapeText(node.output_shapes) || node.kind.replace("Node", ""),
      kind: node.kind,
      depth: node.depth || 0,
      raw: node,
    }));
    return { nodes, edges: expanded ? graph.edges : sequentialEdges(nodes) };
  }
  if (mode === "block" && activeBlock && trace) {
    const prefix = `${activeBlock.qualified_name}.`;
    const operations = trace.operations.filter((operation) => (
      operation.qualified_name === activeBlock.qualified_name || operation.qualified_name.startsWith(prefix)
    ));
    const nodes = operations.map(operationNode);
    return { nodes, edges: sequentialEdges(nodes) };
  }
  if (mode === "block" && blocks) {
    const nodes = blocks.map((block) => ({
      id: block.block_uid,
      title: block.qualified_name,
      subtitle: `${block.block_type} · ${block.dedup_ref.slice(-8)}`,
      kind: "block",
      depth: 0,
      raw: block,
    }));
    return { nodes, edges: sequentialEdges(nodes) };
  }
  if (mode === "source" && trace) {
    const nodes = trace.operations.map(operationNode);
    return { nodes, edges: sequentialEdges(nodes) };
  }
  return { nodes: [], edges: [] };
}

export function layoutGraph(nodes, edges) {
  if (!nodes.length) return new Map();
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target) || edge.source === edge.target) continue;
    incoming.set(edge.target, incoming.get(edge.target) + 1);
    outgoing.get(edge.source).push(edge.target);
  }
  const ranks = new Map(nodes.map((node) => [node.id, 0]));
  const queue = nodes.filter((node) => incoming.get(node.id) === 0).map((node) => node.id);
  const visited = new Set();
  while (queue.length) {
    const id = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    for (const target of outgoing.get(id)) {
      ranks.set(target, Math.max(ranks.get(target), ranks.get(id) + 1));
      incoming.set(target, incoming.get(target) - 1);
      if (incoming.get(target) === 0) queue.push(target);
    }
  }
  let fallbackRank = Math.max(0, ...ranks.values());
  for (const node of nodes) {
    if (!visited.has(node.id)) ranks.set(node.id, ++fallbackRank);
  }
  const rows = new Map();
  for (const node of nodes) {
    const rank = ranks.get(node.id);
    if (!rows.has(rank)) rows.set(rank, []);
    rows.get(rank).push(node);
  }
  const positions = new Map();
  for (const [rank, row] of [...rows].sort((a, b) => a[0] - b[0])) {
    row.forEach((node, column) => positions.set(node.id, { x: 50 + column * 224, y: 44 + rank * 112 }));
  }
  return positions;
}

export function graphBounds(nodes, positions) {
  const values = nodes.map((node) => positions.get(node.id)).filter(Boolean);
  return {
    width: Math.max(300, ...values.map((position) => position.x + 220)),
    height: Math.max(250, ...values.map((position) => position.y + 100)),
  };
}
