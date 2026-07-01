export const NODE_WIDTH = 248;
export const NODE_HEIGHT = 132;

function shapeText(records = []) {
  return records.map((record) => record?.shape || record).filter(Array.isArray)
    .map((shape) => `[${shape.join(", ")}]`).join(" ");
}

function viewNode(raw) {
  const inputs = raw.input_ports || raw.inputs || [];
  const outputs = raw.output_ports || raw.outputs || [];
  return {
    id: raw.id || raw.module_id || raw.block_uid,
    title: raw.display_name || raw.name || raw.qualified_name,
    subtitle: raw.module_path || shapeText(outputs) || raw.kind,
    kind: raw.kind || "module",
    raw,
    inputPorts: inputs,
    outputPorts: outputs,
    layerGroupId: raw.layer_group_id || null,
  };
}

function moduleWithin(module, scope) {
  if (!scope || scope.qualified_name === "<root>") return true;
  const path = module || "";
  return path === scope.qualified_name || path.startsWith(`${scope.qualified_name}.`);
}

function syntheticBoundary(kind, edge, sourceNode, targetNode) {
  const input = kind === "scope_input";
  const id = `${kind}:${edge.tensor_id}`;
  const original = input
    ? targetNode?.input_ports?.find((port) => port.port_id === edge.target_port)
    : sourceNode?.output_ports?.find((port) => port.port_id === edge.source_port);
  const port = {
    ...(original || {}),
    port_id: `${id}:${input ? "out" : "in"}:0`,
    direction: input ? "output" : "input",
    name: original?.name || (input ? "scope input" : "scope output"),
    tensor_id: edge.tensor_id,
    shape: edge.shape,
  };
  return {
    id,
    kind,
    name: input ? "Scope input" : "Scope output",
    display_name: input ? "Scope input" : "Scope output",
    module_path: null,
    layer_group_id: null,
    source_ref: { file: null },
    input_ports: input ? [] : [port],
    output_ports: input ? [port] : [],
    call_arguments: [],
    attributes: {},
  };
}

export function operationProjection(graph, scopeModuleId = null) {
  if (!graph) return { nodes: [], edges: [], layerGroups: [] };
  const modules = new Map(graph.modules.map((module) => [module.module_id, module]));
  const scope = modules.get(scopeModuleId) || modules.get("module-00000") || null;
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const included = new Set(graph.nodes.filter((node) => (
    node.kind === "aten_op" && moduleWithin(node.module_path, scope)
  )).map((node) => node.id));

  if (!scope || scope.qualified_name === "<root>") {
    for (const node of graph.nodes) included.add(node.id);
  } else {
    for (const edge of graph.edges) {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (included.has(edge.target) && source && ["parameter", "buffer"].includes(source.kind)) included.add(source.id);
      if (included.has(edge.source) && target?.kind === "graph_output") included.add(target.id);
      if (included.has(edge.target) && source?.kind === "graph_input") included.add(source.id);
    }
  }

  const projectedNodes = new Map([...included].map((id) => [id, byId.get(id)]).filter(([, node]) => node));
  const projectedEdges = [];
  for (const edge of graph.edges) {
    const sourceIncluded = included.has(edge.source);
    const targetIncluded = included.has(edge.target);
    if (!sourceIncluded && !targetIncluded) continue;
    if (sourceIncluded && targetIncluded) {
      projectedEdges.push({ ...edge });
      continue;
    }
    const kind = targetIncluded ? "scope_input" : "scope_output";
    const boundary = syntheticBoundary(kind, edge, byId.get(edge.source), byId.get(edge.target));
    projectedNodes.set(boundary.id, boundary);
    projectedEdges.push(targetIncluded ? {
      ...edge,
      source: boundary.id,
      source_port: boundary.output_ports[0].port_id,
    } : {
      ...edge,
      target: boundary.id,
      target_port: boundary.input_ports[0].port_id,
    });
  }
  const activeLayers = new Set([...projectedNodes.values()].map((node) => node.layer_group_id).filter(Boolean));
  return {
    nodes: [...projectedNodes.values()].map(viewNode),
    edges: projectedEdges,
    layerGroups: graph.layer_groups.filter((group) => activeLayers.has(group.layer_group_id)),
    scope,
  };
}

function directChildPath(path, scopePath) {
  if (!path || path === "<root>") return "<root>";
  if (!scopePath || scopePath === "<root>") return path.split(".")[0];
  if (path === scopePath) return scopePath;
  const relative = path.slice(scopePath.length + 1);
  return `${scopePath}.${relative.split(".")[0]}`;
}

export function moduleProjection(graph, scopeModuleId = null) {
  const detailed = operationProjection(graph, scopeModuleId);
  if (!graph || !detailed.nodes.length) return detailed;
  const modules = new Map(graph.modules.map((module) => [module.module_id, module]));
  const modulesByPath = new Map(graph.modules.map((module) => [module.qualified_name, module]));
  const callsByModule = new Map();
  for (const call of graph.module_calls || []) {
    if (!callsByModule.has(call.module_id)) callsByModule.set(call.module_id, []);
    callsByModule.get(call.module_id).push(call);
  }
  const groups = new Map(graph.layer_groups.map((group) => [group.layer_group_id, group]));
  const scopePath = detailed.scope?.qualified_name || "<root>";
  const rawById = new Map(detailed.nodes.map((node) => [node.id, node.raw]));

  function owner(node) {
    if (!node) return null;
    if (node.kind !== "aten_op" && !["parameter", "buffer"].includes(node.kind)) return node.id;
    if (node.layer_group_id && groups.has(node.layer_group_id)) {
      const layer = groups.get(node.layer_group_id);
      if (scopePath === "<root>" || !layer.qualified_name.startsWith(`${scopePath}.`) || layer.qualified_name !== scopePath) {
        if (moduleWithin(layer.qualified_name, detailed.scope)) return `group:${layer.module_id}`;
      }
    }
    const path = directChildPath(node.module_path, scopePath);
    const module = modulesByPath.get(path) || modules.get(node.module_id);
    return module ? `group:${module.module_id}` : node.id;
  }

  const ownerByNode = new Map(detailed.nodes.map((node) => [node.id, owner(node.raw)]));
  for (const edge of detailed.edges) {
    const sourceRaw = rawById.get(edge.source);
    if (["parameter", "buffer"].includes(sourceRaw?.kind)) {
      ownerByNode.set(edge.source, ownerByNode.get(edge.target));
    }
  }

  const projected = new Map();
  function ensureOwner(ownerId, raw) {
    if (projected.has(ownerId)) return projected.get(ownerId);
    if (!ownerId.startsWith("group:")) {
      const node = { ...raw, input_ports: [], output_ports: [] };
      projected.set(ownerId, node);
      return node;
    }
    const moduleId = ownerId.slice(6);
    const module = modules.get(moduleId);
    const node = {
      id: ownerId,
      kind: "module_group",
      name: module?.qualified_name || ownerId,
      display_name: module?.display_name || ownerId,
      module_id: moduleId,
      module_path: module?.qualified_name,
      qualified_name: module?.qualified_name,
      layer_group_id: module?.layer_group_id || null,
      source_ref: module?.source_ref || { file: null },
      constructor: module?.constructor || {},
      parameters: module?.parameters || [],
      input_ports: [],
      output_ports: [],
      call_arguments: [],
      attributes: {},
    };
    projected.set(ownerId, node);
    return node;
  }

  for (const node of detailed.nodes) ensureOwner(ownerByNode.get(node.id), node.raw);
  const inputPortKeys = new Map();
  const outputPortKeys = new Map();
  const edges = [];
  function callBoundaryPort(ownerId, direction, tensorId) {
    if (!ownerId.startsWith("group:")) return null;
    const calls = callsByModule.get(ownerId.slice(6)) || [];
    const ordered = direction === "input" ? calls : [...calls].reverse();
    for (const call of ordered) {
      const ports = direction === "input" ? call.input_ports : call.output_ports;
      const match = ports.find((port) => port.tensor_id === tensorId);
      if (match) return match;
    }
    return null;
  }
  for (const edge of detailed.edges) {
    const sourceOwner = ownerByNode.get(edge.source);
    const targetOwner = ownerByNode.get(edge.target);
    if (!sourceOwner || !targetOwner || sourceOwner === targetOwner) continue;
    const source = ensureOwner(sourceOwner, rawById.get(edge.source));
    const target = ensureOwner(targetOwner, rawById.get(edge.target));
    const sourceRaw = rawById.get(edge.source);
    const targetRaw = rawById.get(edge.target);
    const originalOutput = callBoundaryPort(sourceOwner, "output", edge.tensor_id)
      || sourceRaw?.output_ports?.find((port) => port.port_id === edge.source_port) || {};
    const originalInput = callBoundaryPort(targetOwner, "input", edge.tensor_id)
      || targetRaw?.input_ports?.find((port) => port.port_id === edge.target_port) || {};
    const outputKey = `${sourceOwner}:${edge.tensor_id}`;
    const inputKey = `${targetOwner}:${edge.target_port}:${edge.tensor_id}`;
    if (!outputPortKeys.has(outputKey)) {
      const port = {
        ...originalOutput,
        port_id: `${sourceOwner}:out:${source.output_ports.length}`,
        direction: "output",
        tensor_id: edge.tensor_id,
        shape: edge.shape,
      };
      source.output_ports.push(port);
      outputPortKeys.set(outputKey, port);
    }
    if (!inputPortKeys.has(inputKey)) {
      const port = {
        ...originalInput,
        port_id: `${targetOwner}:in:${target.input_ports.length}`,
        direction: "input",
        tensor_id: edge.tensor_id,
        shape: edge.shape,
      };
      target.input_ports.push(port);
      inputPortKeys.set(inputKey, port);
    }
    edges.push({
      ...edge,
      edge_id: `group:${edge.edge_id}`,
      source: sourceOwner,
      source_port: outputPortKeys.get(outputKey).port_id,
      target: targetOwner,
      target_port: inputPortKeys.get(inputKey).port_id,
    });
  }
  const activeLayers = new Set([...projected.values()].map((node) => node.layer_group_id).filter(Boolean));
  return {
    nodes: [...projected.values()].filter((node) => (
      node.input_ports.length || node.output_ports.length || node.kind === "graph_input" || node.kind === "graph_output"
    )).map(viewNode),
    edges,
    layerGroups: graph.layer_groups.filter((group) => activeLayers.has(group.layer_group_id)),
    scope: detailed.scope,
  };
}

export function projectGraph({ mode, current, family, index, graph, scopeModuleId }) {
  if (!current) return { nodes: [], edges: [], layerGroups: [] };
  if (mode === "family") {
    const root = {
      id: `family:${current.family_id}`,
      name: current.family_name,
      display_name: current.family_name,
      kind: "family",
      input_ports: [],
      output_ports: [],
    };
    const versions = (family?.versions || [current.version_id]).map((versionId) => {
      const summary = index.find((item) => item.version_id === versionId) || current;
      return {
        id: `version:${versionId}`,
        name: summary.family_name || current.family_name,
        display_name: summary.family_name || current.family_name,
        kind: "version",
        qualified_name: versionId,
        input_ports: [],
        output_ports: [],
        parameters: summary.parameters || current.parameters?.total,
      };
    });
    return {
      nodes: [root, ...versions].map(viewNode),
      edges: versions.map((node, indexValue) => ({
        edge_id: `family-edge-${indexValue}`,
        source: root.id,
        source_port: null,
        target: node.id,
        target_port: null,
        tensor_id: null,
        shape: [],
        confidence: "exact",
      })),
      layerGroups: [],
    };
  }
  return mode === "operation"
    ? operationProjection(graph, scopeModuleId)
    : moduleProjection(graph, scopeModuleId);
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
  for (const node of nodes) if (!visited.has(node.id)) ranks.set(node.id, ++fallbackRank);
  const rows = new Map();
  for (const node of nodes) {
    const rank = ranks.get(node.id);
    if (!rows.has(rank)) rows.set(rank, []);
    rows.get(rank).push(node);
  }
  const positions = new Map();
  for (const [rank, row] of [...rows].sort((left, right) => left[0] - right[0])) {
    row.sort((left, right) => (left.raw?.module_path || left.title).localeCompare(right.raw?.module_path || right.title));
    row.forEach((node, column) => positions.set(node.id, {
      x: 70 + column * (NODE_WIDTH + 54),
      y: 62 + rank * (NODE_HEIGHT + 70),
    }));
  }
  return positions;
}

export function graphBounds(nodes, positions) {
  const values = nodes.map((node) => positions.get(node.id)).filter(Boolean);
  return {
    width: Math.max(400, ...values.map((position) => position.x + NODE_WIDTH + 80)),
    height: Math.max(300, ...values.map((position) => position.y + NODE_HEIGHT + 80)),
  };
}
