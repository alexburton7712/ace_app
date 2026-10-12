import type { Snapshot } from "./types";

type Listener = (snapshot: Snapshot) => void;

export class SnapshotStore {
  private current: Snapshot | null = null;
  private listeners = new Set<Listener>();

  apply(next: Snapshot): boolean {
    if (!Number.isInteger(next?.revision)) return false;
    if (this.current && next.revision < this.current.revision) return false;
    this.current = next;
    this.listeners.forEach((listener) => listener(next));
    return true;
  }

  get(): Snapshot | null { return this.current; }
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    if (this.current) listener(this.current);
    return () => this.listeners.delete(listener);
  }
}
