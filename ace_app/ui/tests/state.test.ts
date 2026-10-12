import { describe, expect, it, vi } from "vitest";
import { SnapshotStore } from "../src/state";
import type { Snapshot } from "../src/types";

const snapshot = (revision: number): Snapshot => ({
  schema_version: 1, revision, active_target: "local", operation: { state: "idle" },
  history: { turns: [], assumed_context_turns: 10 }, widgets: [], connections: {}, notices: [],
});

describe("SnapshotStore", () => {
  it("does not allow stale events to roll the UI backward", () => {
    const store = new SnapshotStore();
    const listener = vi.fn();
    store.subscribe(listener);
    expect(store.apply(snapshot(9))).toBe(true);
    expect(store.apply(snapshot(8))).toBe(false);
    expect(store.get()?.revision).toBe(9);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
