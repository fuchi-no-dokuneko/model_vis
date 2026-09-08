export function savedReviews({ snapshot, restore, status }) {
  const key = "model-vis-reviews";
  let items;
  try { items = JSON.parse(localStorage.getItem(key) || "[]"); }
  catch { items = []; }
  if (!Array.isArray(items)) items = [];
  const list = document.querySelector("#saved-reviews");
  function persist() {
    try { localStorage.setItem(key, JSON.stringify(items)); status("View saved in this browser."); }
    catch { status("Browser storage unavailable. Views remain available for this session; export to retain them."); }
  }
  function render() {
    list.replaceChildren();
    if (!items.length) list.textContent = "No saved views yet.";
    items.forEach((item, index) => {
      const row = document.createElement("div"), open = document.createElement("button"), remove = document.createElement("button");
      open.textContent = item.name;
      open.addEventListener("click", () => restore(item));
      remove.textContent = "Delete"; remove.setAttribute("aria-label", `Delete saved view ${item.name}`);
      remove.addEventListener("click", () => { items.splice(index, 1); persist(); render(); });
      row.append(open, remove); list.append(row);
    });
  }
  document.querySelector("#save-review").addEventListener("click", () => {
    const item = snapshot();
    if (!item) return;
    items.push(item); persist(); render();
  });
  render();
}
