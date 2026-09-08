export function panelState(container, message, { error, retry, retryLabel = "Retry" } = {}) {
  const section = document.createElement("div");
  section.className = "resource-state";
  section.setAttribute("role", error ? "alert" : "status");
  const title = document.createElement("p");
  title.textContent = message;
  section.append(title);
  if (retry) {
    const button = document.createElement("button");
    button.textContent = retryLabel;
    button.addEventListener("click", retry);
    section.append(button);
  }
  if (error) {
    const details = document.createElement("details"), summary = document.createElement("summary"), text = document.createElement("pre");
    summary.textContent = "Diagnostic details";
    text.textContent = error.message;
    details.append(summary, text);
    section.append(details);
  }
  container.replaceChildren(section);
}
