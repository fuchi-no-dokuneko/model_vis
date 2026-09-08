import { flattenConfig } from "./data-store.js";
import { panelState } from "./panel-state.js";

export function compareDetails(container, left, right, semantics, store, appendTable) {
  const details = document.createElement("details"), summary = document.createElement("summary"), select = document.createElement("select"), fields = document.createElement("div");
  details.className = "comparison-details"; summary.textContent = "Configuration field comparison";
  select.setAttribute("aria-label", "Comparison configuration scope");
  for (const value of ["trace", "official"]) { const option = new Option(value === "trace" ? "Trace configuration" : "Pinned checkpoint configuration", value); select.append(option); }
  let token = 0;
  async function render() {
    const current = ++token;
    panelState(fields, "Loading configuration fields…");
    try {
      const configs = await Promise.all([left, right].map((version) => select.value === "trace" ? store.traceConfig(version) : store.officialConfig(version)));
      if (current !== token) return;
      if (configs.some((config) => !config)) { panelState(fields, "Not comparable: a selected model has no pinned configuration."); return; }
      const [a, b] = configs.map((config) => flattenConfig(config.config || config));
      const rows = [...new Set([...a.keys(), ...b.keys()])].sort().map((key) => [key, a.get(key), b.get(key)]);
      fields.replaceChildren(); appendTable(fields, rows, left.family_name, right.family_name);
      container.dispatchEvent(new Event("comparisonrender"));
    } catch (error) { if (current === token) panelState(fields, "Configuration comparison failed.", { error, retry: render }); }
  }
  select.addEventListener("change", render);
  details.addEventListener("toggle", () => { if (details.open && !fields.childElementCount) render(); });
  details.append(summary, select, fields); container.append(details);
  semantics.forEach((semantic, index) => {
    const journey = semantic.journeys?.[0]; if (!journey) return;
    const fold = document.createElement("details"), heading = document.createElement("summary"), list = document.createElement("ol");
    fold.className = "comparison-details";
    heading.textContent = `${[left, right][index].family_name} Primary journey · ${JSON.stringify(journey.steps[0].shape)} → ${JSON.stringify(journey.steps.at(-1).shape)} · ${journey.steps.length} steps · ${journey.route_confidence}`;
    for (const step of journey.steps) { const item = document.createElement("li"); item.textContent = `${step.transform}: ${step.explanation}`; list.append(item); }
    fold.append(heading, list); container.append(fold);
  });
}
