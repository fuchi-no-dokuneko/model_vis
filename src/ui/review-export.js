export function reviewFacts(state, link, annotation) {
  const selected = new Set([...state.selectedIds, state.selectedId].filter(Boolean));
  for (const stage of state.semantic?.stages || []) {
    if (selected.has(stage.stage_id)) stage.operation_ids.forEach((id) => selected.add(id));
  }
  const nodes = (state.graph?.nodes || []).filter((node) => selected.has(node.id));
  const ids = new Set(nodes.map((node) => node.id));
  const edges = (state.graph?.edges || []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const boundaryEdges = (state.graph?.edges || []).filter((edge) => ids.has(edge.source) !== ids.has(edge.target));
  return {
    title: "Model structure investigation",
    link,
    annotation,
    model: state.current?.version_id,
    entrypoint: state.current?.parameter_evidence?.model_class,
    provenance: state.current?.official_config_source || null,
    parameter_evidence: state.current?.parameter_evidence || null,
    trace_scope: state.current?.execution_mode,
    trace_origin: state.current?.execution_source_version,
    weights: "Initialized; pretrained outputs unverified",
    view: { mode: state.mode, detail: state.detailMode, labels: state.labelMode },
    selection: [...selected],
    nodes, edges, boundary_edges: boundaryEdges,
  };
}

export function factsCsv(facts) {
  const columns = ["model", "operation_id", "interface", "module_path", "input_ports", "output_ports", "checkpoint", "revision", "trace_scope", "annotation"];
  const rows = facts.nodes.map((node) => [facts.model, node.id, node.display_name || node.name, node.module_path,
    JSON.stringify(node.input_ports), JSON.stringify(node.output_ports), facts.provenance?.repo_id,
    facts.provenance?.revision, facts.trace_scope, facts.annotation]);
  return [columns, ...rows].map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
}

export function downloadReview(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
