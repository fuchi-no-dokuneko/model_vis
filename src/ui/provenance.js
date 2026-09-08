export function evidenceRows(version, semantic) {
  const source = version.official_config_source;
  const count = version.parameter_evidence || {};
  const reused = version.execution_source_version !== version.version_id;
  const rows = [
    ["Checkpoint", source?.repo_id || "Unverified; no pinned mapping"],
    ["Revision", source?.revision || "Unavailable"],
    ["Traced entrypoint", count.model_class || "Unavailable"],
    ["Trace scope", version.execution_mode === "full_model_forward" ? "Full configured model forward" : "Compact unique structure demonstration"],
    ["Weights", "Initialized; pretrained weights were not downloaded"],
    ["Trace origin", reused ? `Architecture demonstration: trace reused from ${version.execution_source_version}; selected checkpoint not verified` : version.version_id],
    ["Config-derived parameters", count.parameter_count?.toLocaleString() || "Unavailable"],
    ["Counting basis", count.parameter_count == null ? count.reason || "Unavailable" : count.basis],
    ["Head scope", count.head_scope || "Unavailable"],
    ["Publisher parameter count", "Unavailable; no publisher count verified"],
    ["Preflight estimate", `${version.resource_preflight?.estimated_parameter_count?.toLocaleString() || "Unavailable"} parameters; approximate memory-planning input`],
    ["Mapping review", source?.mapping_status || "Missing"],
  ];
  for (const variant of count.variants || []) rows.push([variant.model_class, `${variant.parameter_count.toLocaleString()} parameters · ${variant.head_scope}`]);
  if (semantic) {
    rows.push(["Verified semantic rules", `${Math.round(100 * semantic.coverage.verified_module_fraction)}% of modules`]);
    rows.push(["Class tags", `${Math.round(100 * semantic.coverage.class_tag_fraction)}% classified; remaining modules use technical names`]);
    rows.push(["Verification scope", "Asset integrity and initialized architecture execution; pretrained outputs and numerical equivalence unverified"]);
  }
  return rows;
}

export function renderEvidence(container, version, semantic) {
  const list = document.createElement("dl");
  list.className = "evidence-facts";
  for (const [key, value] of evidenceRows(version, semantic)) {
    const term = document.createElement("dt"), detail = document.createElement("dd");
    term.textContent = key; detail.textContent = value;
    list.append(term, detail);
  }
  container.replaceChildren(list);
}
