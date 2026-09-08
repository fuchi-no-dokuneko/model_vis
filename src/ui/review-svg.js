const escape = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");

export function subgraphSvg(facts) {
  const width = 640, rowHeight = 100, height = Math.max(180, facts.nodes.length * rowHeight + 100);
  const nodes = facts.nodes.map((node, index) => {
    const y = 70 + index * rowHeight;
    return `<g id="${escape(node.id)}"><rect x="25" y="${y}" width="590" height="80" rx="6" fill="#f2f7f4" stroke="#08785d"/><text x="38" y="${y + 25}">${escape(node.display_name || node.name || node.id)}</text><text x="38" y="${y + 48}" font-size="12">${escape(node.module_path || node.id)}</text><title>${escape(JSON.stringify({ inputs: node.input_ports, outputs: node.output_ports }))}</title></g>`;
  });
  const ids = new Map(facts.nodes.map((node, index) => [node.id, index]));
  const edges = facts.edges.map((edge) => `<path d="M 615 ${110 + ids.get(edge.source) * rowHeight} C 635 ${110 + ids.get(edge.source) * rowHeight},635 ${110 + ids.get(edge.target) * rowHeight},615 ${110 + ids.get(edge.target) * rowHeight}" fill="none" stroke="#356a9b"><title>${escape(edge.tensor_id)}</title></path>`);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><metadata>${escape(JSON.stringify(facts))}</metadata><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" fill="#172b21"><text x="25" y="25">${escape(facts.model)} · initialized architecture</text><text x="25" y="47" font-size="12">${escape(facts.annotation || "Selected subgraph; full facts embedded in metadata")}</text>${nodes.join("")}${edges.join("")}</g></svg>`;
}
