import type { Envelope, Snapshot, Target } from "./types";

type Reply = (json: string) => void;
interface NativeBridge {
  get_snapshot(capability: string, reply: Reply): void;
  select_target(capability: string, target: string, reply: Reply): void;
  start_recording(capability: string, reply: Reply): void;
  stop_and_send(capability: string, reply: Reply): void;
  clear_conversation(capability: string, target: string, reply: Reply): void;
  dismiss_widget(capability: string, id: string, reply: Reply): void;
}

let native: NativeBridge | null = null;
let secret = "";
let readyResolve: (() => void) | null = null;
const ready = new Promise<void>((resolve) => { readyResolve = resolve; });

function invoke<T>(method: keyof NativeBridge, ...args: string[]): Promise<Envelope<T>> {
  return ready.then(() => new Promise((resolve) => {
    if (!native) {
      resolve({ ok: false, error: { code: "bridge_unavailable", message: "Native bridge unavailable" } });
      return;
    }
    const callback: Reply = (wire) => {
      try { resolve(JSON.parse(wire) as Envelope<T>); }
      catch { resolve({ ok: false, error: { code: "invalid_response", message: "Native bridge returned invalid data" } }); }
    };
    const fn = native[method] as (...parts: (string | Reply)[]) => void;
    fn.call(native, secret, ...args, callback);
  }));
}

export const commands = {
  snapshot: () => invoke<Snapshot>("get_snapshot"),
  selectTarget: (target: Target) => invoke("select_target", target),
  startRecording: () => invoke("start_recording"),
  stopAndSend: () => invoke("stop_and_send"),
  clearConversation: (target: Target) => invoke("clear_conversation", target),
  dismissWidget: (id: string) => invoke("dismiss_widget", id),
};

window.__ACE_NATIVE_CONNECT__ = (bridge: NativeBridge, capability: string) => {
  if (native) return;
  native = bridge;
  secret = capability;
  readyResolve?.();
  readyResolve = null;
  window.dispatchEvent(new Event("ace-bridge-ready"));
};

declare global {
  interface Window {
    __ACE_NATIVE_CONNECT__: (bridge: NativeBridge, capability: string) => void;
    __ACE_DESKTOP__: { receiveSnapshot(snapshot: Snapshot): void };
  }
}
