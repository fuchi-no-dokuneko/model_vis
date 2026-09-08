export function workspaceSizing(status) {
  const key = "model-vis-panel-widths";
  let saved = { sidebar: 260, inspector: 370 };
  try { Object.assign(saved, JSON.parse(localStorage.getItem(key) || "{}")); } catch { /* defaults */ }
  const root = document.documentElement;
  function apply() {
    const available = Math.max(500, innerWidth - 320);
    const sidebar = Math.max(180, Math.min(Number(saved.sidebar) || 260, available - 280));
    const inspector = Math.max(280, Math.min(Number(saved.inspector) || 370, available - sidebar));
    for (const [name, width] of Object.entries({ sidebar, inspector })) {
      root.style.setProperty(`--${name}-width`, `${width}px`);
      document.querySelector(`#resize-${name}`).setAttribute("aria-valuenow", String(width));
    }
  }
  function persist() {
    try { localStorage.setItem(key, JSON.stringify(saved)); }
    catch { status("Panel sizes apply for this session; browser storage is unavailable."); }
  }
  for (const name of ["sidebar", "inspector"]) {
    const handle = document.querySelector(`#resize-${name}`);
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault(); handle.setPointerCapture(event.pointerId);
      const update = (move) => {
        saved[name] = name === "sidebar" ? move.clientX : innerWidth - move.clientX;
        apply();
      };
      const end = () => { handle.removeEventListener("pointermove", update); persist(); };
      handle.addEventListener("pointermove", update);
      handle.addEventListener("pointerup", end, { once: true });
      handle.addEventListener("pointercancel", end, { once: true });
    });
    handle.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      saved[name] += (event.key === "ArrowRight" ? 16 : -16) * (name === "sidebar" ? 1 : -1);
      apply(); persist();
    });
  }
  document.querySelector("#reset-panels").addEventListener("click", () => {
    saved = { sidebar: 260, inspector: 370 }; apply(); persist();
  });
  window.addEventListener("resize", apply); apply();
}
