import type { Notice } from "./types";

export function renderNotices(container: HTMLElement, notices: Notice[]): void {
  container.replaceChildren(...notices.slice(-4).map((notice) => {
    const item = document.createElement("div");
    item.className = `notice notice-${notice.level ?? "info"}`;
    const message = document.createElement("p");
    message.textContent = notice.message;
    item.append(message);
    if (notice.details) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Details";
      const copy = document.createElement("p");
      copy.textContent = notice.details;
      details.append(summary, copy);
      item.append(details);
    }
    return item;
  }));
}

export function localNotice(container: HTMLElement, messageText: string, level = "error"): void {
  const item = document.createElement("div");
  item.className = `notice notice-${level}`;
  item.textContent = messageText;
  container.append(item);
  window.setTimeout(() => item.remove(), 6_000);
}
