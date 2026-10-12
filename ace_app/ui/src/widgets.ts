import type { WidgetRecord } from "./types";

export const WIDGET_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; form-action 'none'; base-uri 'none'";

export function widgetDocument(html: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${WIDGET_CSP}"><meta name="referrer" content="no-referrer"><style>html{color-scheme:light dark}body{margin:0;padding:16px;font:15px/1.5 system-ui,sans-serif;overflow-wrap:anywhere}</style></head><body>${html}</body></html>`;
}

export class WidgetRenderer {
  private cards = new Map<string, { card: HTMLElement; revision: number | undefined }>();
  constructor(private grid: HTMLElement, private empty: HTMLElement, private count: HTMLElement, private onDismiss: (id: string, button: HTMLButtonElement) => void) {}

  render(records: WidgetRecord[]): void {
    const ids = new Set(records.map((record) => record.id));
    this.cards.forEach(({ card }, id) => { if (!ids.has(id)) { card.remove(); this.cards.delete(id); } });
    records.forEach((record) => {
      const existing = this.cards.get(record.id);
      if (!existing) this.create(record);
      else if (existing.revision !== record.revision) this.replaceFrame(existing.card, record);
      this.grid.append(this.cards.get(record.id)!.card); // authoritative insertion order
    });
    this.empty.hidden = records.length > 0;
    this.grid.hidden = records.length === 0;
    this.count.textContent = String(records.length);
  }

  private create(record: WidgetRecord): void {
    const card = document.createElement("article");
    card.className = "widget-card";
    card.dataset.widgetId = record.id;
    const header = document.createElement("header");
    const identity = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = record.id;
    const badge = document.createElement("span");
    badge.className = `target-badge target-${record.source_target}`;
    badge.textContent = record.source_target === "local" ? "Local Ace" : "Server Ace";
    identity.append(title, badge);
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "dismiss-widget";
    dismiss.setAttribute("aria-label", `Dismiss ${record.id} widget`);
    dismiss.textContent = "×";
    dismiss.addEventListener("click", () => this.onDismiss(record.id, dismiss));
    header.append(identity, dismiss);
    const body = document.createElement("div");
    body.className = "widget-body";
    card.append(header, body);
    this.cards.set(record.id, { card, revision: record.revision });
    this.replaceFrame(card, record);
  }

  private replaceFrame(card: HTMLElement, record: WidgetRecord): void {
    const body = card.querySelector<HTMLElement>(".widget-body")!;
    const loading = document.createElement("div");
    loading.className = "widget-loading";
    loading.textContent = "Loading widget…";
    const frame = document.createElement("iframe");
    frame.className = "widget-frame";
    frame.title = `${record.id} interactive widget`;
    frame.setAttribute("sandbox", "allow-scripts");
    frame.referrerPolicy = "no-referrer";
    frame.srcdoc = widgetDocument(record.html);
    const timeout = window.setTimeout(() => {
      loading.className = "widget-error";
      loading.textContent = "This widget took too long to render.";
      frame.hidden = true;
    }, 8_000);
    frame.addEventListener("load", () => { window.clearTimeout(timeout); loading.remove(); }, { once: true });
    body.replaceChildren(loading, frame);
    const tracked = this.cards.get(record.id);
    if (tracked) tracked.revision = record.revision;
  }
}
