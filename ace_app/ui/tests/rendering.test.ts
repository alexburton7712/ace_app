import { describe, expect, it, vi } from "vitest";
import { renderConversation } from "../src/conversation";
import { WidgetRenderer, WIDGET_CSP, widgetDocument } from "../src/widgets";

describe("safe frontend rendering", () => {
  it("renders transcript content as text", () => {
    const root = document.createElement("div");
    renderConversation(root, [{ role: "assistant", text: "<img src=x onerror=alert(1)>" }], 10);
    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toContain("<img src=x");
  });

  it("expands persisted paired turns into user and Ace messages", () => {
    const root = document.createElement("div");
    renderConversation(root, [{ user_text: "hello", assistant_text: "hi" }], 10);
    expect(root.querySelectorAll(".message")).toHaveLength(2);
    expect(root.textContent).toContain("hello");
    expect(root.textContent).toContain("hi");
  });

  it("creates a script-only opaque sandbox with CSP", () => {
    expect(widgetDocument("<p>hello</p>")).toContain(WIDGET_CSP);
    const grid = document.createElement("div");
    const empty = document.createElement("div");
    const count = document.createElement("span");
    const renderer = new WidgetRenderer(grid, empty, count, vi.fn());
    renderer.render([{ id: "safe-id", html: "<p>hello</p>", source_target: "local", revision: 1 }]);
    const frame = grid.querySelector("iframe")!;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame.referrerPolicy).toBe("no-referrer");
  });

  it("replaces an iframe without moving the card", () => {
    const grid = document.createElement("div");
    const renderer = new WidgetRenderer(grid, document.createElement("div"), document.createElement("span"), vi.fn());
    renderer.render([
      { id: "one", html: "old", source_target: "local", revision: 1 },
      { id: "two", html: "two", source_target: "server", revision: 1 },
    ]);
    const firstCard = grid.firstElementChild;
    const firstFrame = firstCard!.querySelector("iframe");
    renderer.render([
      { id: "one", html: "new", source_target: "local", revision: 2 },
      { id: "two", html: "two", source_target: "server", revision: 1 },
    ]);
    expect(grid.firstElementChild).toBe(firstCard);
    expect(firstCard!.querySelector("iframe")).not.toBe(firstFrame);
  });
});
