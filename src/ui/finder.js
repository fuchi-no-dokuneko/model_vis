const normalized = (value) => String(value || "").toLowerCase().replaceAll(/\s+/g, "");

export function operationRecords(graph) {
  const modules = new Map((graph?.modules || []).map((module) => [module.module_id, module]));
  return (graph?.nodes || []).map((node) => {
    const ports = [...(node.input_ports || []), ...(node.output_ports || [])];
    return {
      id: node.id,
      interface: node.display_name || node.name || node.kind,
      module: node.module_path || "<root>",
      tensor: [...new Set(ports.map((p) => p.tensor_id).filter(Boolean))].join(" "),
      dtype: [...new Set(ports.map((p) => p.dtype).filter(Boolean))].join(" "),
      shape: [...new Set(ports.map((p) => JSON.stringify(p.shape)))].join(" "),
      source: [node.source_ref?.symbol, modules.get(node.module_id)?.class_name, ...ports.map((port) => port.name)].filter(Boolean).join(" "),
      node,
    };
  });
}

export function findOperations(records, filters) {
  const ports = Object.entries(filters).filter(([key, value]) => value && ["tensor", "dtype", "shape"].includes(key));
  return records.filter((record) => (!ports.length || [...(record.node.input_ports || []), ...(record.node.output_ports || [])].some((port) => ports.every(([key, value]) => {
    const actual = key === "tensor" ? port.tensor_id : key === "shape" ? JSON.stringify(port.shape) : port.dtype;
    return normalized(actual).includes(normalized(value));
  }))) && Object.entries(filters).every(([key, value]) => {
    if (!value) return true;
    const actual = key === "query" ? [record.id, record.interface, record.module, record.tensor, record.dtype, record.shape, record.source].join(" ") : record[key];
    return normalized(actual).includes(normalized(value));
  }));
}

export function renderResults(container, records, page, selectedId, select) {
  const table = document.createElement("table");
  table.className = "finder-table";
  const head = table.createTHead().insertRow();
  for (const title of ["Operation / boundary", "Module", "Tensor IDs", "Dtype", "Shapes"]) {
    const cell = document.createElement("th"); cell.textContent = title; head.append(cell);
  }
  const body = table.createTBody();
  records.slice(page * 30, page * 30 + 30).forEach((record) => {
    const row = body.insertRow(); row.dataset.id = record.id;
    row.classList.toggle("selected", record.id === selectedId);
    const button = document.createElement("button");
    button.textContent = `${record.interface} · ${record.id}`;
    button.addEventListener("click", () => select(record));
    row.insertCell().append(button);
    for (const value of [record.module, record.tensor, record.dtype, record.shape]) row.insertCell().textContent = value || "Unavailable";
  });
  container.replaceChildren(table);
}
