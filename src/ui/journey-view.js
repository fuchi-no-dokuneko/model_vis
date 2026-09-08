const shapes = (ports) => ports?.map((p) => `[${(p.shape || []).join(", ")}]`).join(" + ") || "∅";

export function journeyView(journey, selectedId, focus) {
  const section = document.createElement("section"); section.className = "journey";
  const title = document.createElement("h3");
  title.textContent = `Tensor Journey · ${journey.route_confidence} route`;
  const note = document.createElement("p"); note.className = "journey-meta";
  note.textContent = "Each card describes one operation's observed ports. This primary path follows one branch; other inputs and consumers remain listed.";
  const toggle = document.createElement("button");
  const steps = document.createElement("div"); steps.className = "journey-steps"; steps.tabIndex = 0;
  steps.setAttribute("aria-label", "Scrollable operation journey");
  let expanded = false;
  function render() {
    steps.replaceChildren();
    const active = journey.steps.findIndex((step) => step.node_id === selectedId);
    const visible = new Set([0, 1, journey.steps.length - 1, active - 1, active, active + 1]);
    toggle.textContent = expanded ? "Condense journey" : `Show all ${journey.steps.length} steps`;
    toggle.setAttribute("aria-expanded", String(expanded));
    let skipped = 0;
    journey.steps.forEach((step, index) => {
      if (!expanded && !visible.has(index)) { skipped++; return; }
      if (skipped) {
        const gap = document.createElement("span"); gap.className = "journey-gap";
        gap.textContent = `${skipped} intervening steps hidden`; steps.append(gap); skipped = 0;
      }
      const button = document.createElement("button"); button.className = "journey-step";
      button.classList.toggle("active", step.node_id === selectedId);
      button.dataset.nodeId = step.node_id;
      const parts = [
        ["journey-representation", step.transform],
        ["journey-shape", `${shapes(step.input_ports)} → ${shapes(step.output_ports)}`],
        ["journey-meta", step.explanation],
        ["journey-meta", `${step.dtype} · ${step.route_confidence} tensor route`],
        ["journey-meta", `Input producers: ${step.producer_node_ids?.join(", ") || "model input"}`],
        ["journey-meta", `Output consumers: ${step.consumer_node_ids?.join(", ") || "model output"}`],
      ];
      for (const [className, text] of parts) { const span = document.createElement("span"); span.className = className; span.textContent = text; button.append(span); }
      button.addEventListener("click", () => focus(step)); steps.append(button);
    });
  }
  toggle.addEventListener("click", () => { expanded = !expanded; render(); });
  render(); section.append(title, note, toggle, steps); return section;
}
