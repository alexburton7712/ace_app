import { commands } from "./bridge";
import { renderConversation } from "./conversation";
import { localNotice, renderNotices } from "./notifications";
import { SnapshotStore } from "./state";
import type { Envelope, Snapshot, Target } from "./types";
import { WidgetRenderer } from "./widgets";
import "./styles.css";

const required = <T extends Element>(selector: string): T => {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`Missing required UI element: ${selector}`);
  return node;
};

const store = new SnapshotStore();
const transcript = required<HTMLElement>("#transcript");
const recordButton = required<HTMLButtonElement>("#record-button");
const recordLabel = required<HTMLElement>("#record-label");
const recordTimer = required<HTMLElement>("#recording-timer");
const clearButton = required<HTMLButtonElement>("#clear-button");
const clearDialog = required<HTMLDialogElement>("#clear-dialog");
const clearCopy = required<HTMLElement>("#clear-dialog-copy");
const notices = required<HTMLElement>("#notices");
const liveRegion = required<HTMLElement>("#live-region");
const connection = required<HTMLElement>("#connection-status");
const targetButtons = [...document.querySelectorAll<HTMLButtonElement>(".target-button")];

async function handle(result: Envelope<unknown>): Promise<boolean> {
  if (result.ok) return true;
  localNotice(notices, result.error.message);
  return false;
}

const widgets = new WidgetRenderer(
  required("#widget-grid"), required("#widget-empty"), required("#widget-count"),
  async (id, button) => {
    button.disabled = true;
    if (!(await handle(await commands.dismissWidget(id)))) button.disabled = false;
  },
);

let timer: number | null = null;
let recordingStarted = 0;
let pointerStarted = 0;
let suppressClick = false;

function announce(message: string): void {
  liveRegion.textContent = "";
  window.setTimeout(() => { liveRegion.textContent = message; }, 20);
}

function updateTimer(startedAt?: string): void {
  if (timer !== null) window.clearInterval(timer);
  timer = null;
  if (!startedAt) { recordTimer.textContent = "00:00"; return; }
  recordingStarted = new Date(startedAt).getTime() || Date.now();
  const tick = () => {
    const seconds = Math.max(0, Math.floor((Date.now() - recordingStarted) / 1000));
    recordTimer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  };
  tick(); timer = window.setInterval(tick, 1_000);
}

store.subscribe((snapshot) => {
  const state = snapshot.operation.state;
  const busy = state !== "idle";
  document.body.dataset.operation = state;
  targetButtons.forEach((button) => {
    const selected = button.dataset.target === snapshot.active_target;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
    button.disabled = busy;
  });
  clearButton.disabled = busy || snapshot.history.turns.length === 0;
  recordButton.disabled = state === "sending" || state === "clearing" || state === "shutting_down";
  recordLabel.textContent = state === "recording" ? "Stop and send" : state === "sending" ? "Sending…" : "Record message";
  recordButton.setAttribute("aria-pressed", String(state === "recording"));
  recordButton.classList.toggle("is-recording", state === "recording");
  recordTimer.hidden = state !== "recording";
  updateTimer(state === "recording" ? snapshot.operation.started_at : undefined);
  renderConversation(transcript, snapshot.history.turns, snapshot.history.assumed_context_turns);
  widgets.render(snapshot.widgets);
  renderNotices(notices, snapshot.notices ?? []);
  const localState = snapshot.connections?.local_widget_listener ?? "unavailable";
  const connectionText = localState === "connected" ? "Ready" : `Widgets ${localState.replaceAll("_", " ")}`;
  connection.lastElementChild!.textContent = connectionText;
  connection.classList.toggle("is-ready", localState === "connected");
});

window.__ACE_DESKTOP__ = {
  receiveSnapshot(snapshot: Snapshot) {
    const before = store.get()?.operation.state;
    if (!store.apply(snapshot)) return;
    const after = snapshot.operation.state;
    if (before && before !== after) {
      if (after === "recording") announce("Recording started");
      else if (before === "sending" && after === "idle") announce("Ace response received");
      else if (after === "sending") announce("Recording stopped. Sending to Ace.");
    }
  },
};

window.addEventListener("ace-bridge-ready", async () => {
  const result = await commands.snapshot();
  if (result.ok) store.apply(result.value);
  else localNotice(notices, result.error.message);
}, { once: true });

targetButtons.forEach((button) => button.addEventListener("click", async () => {
  const target = button.dataset.target as Target;
  if (target && target !== store.get()?.active_target) await handle(await commands.selectTarget(target));
}));

async function toggleRecording(): Promise<void> {
  const state = store.get()?.operation.state;
  if (state === "recording") await handle(await commands.stopAndSend());
  else if (state === "idle") await handle(await commands.startRecording());
}

recordButton.addEventListener("click", async () => {
  if (suppressClick) { suppressClick = false; return; }
  await toggleRecording();
});

recordButton.addEventListener("pointerdown", async (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  if (store.get()?.operation.state !== "idle") return;
  pointerStarted = performance.now();
  recordButton.setPointerCapture(event.pointerId);
  suppressClick = true;
  await handle(await commands.startRecording());
});

recordButton.addEventListener("pointerup", async () => {
  if (!pointerStarted) return;
  const heldFor = performance.now() - pointerStarted;
  pointerStarted = 0;
  // A quick tap enters click/tap mode. A deliberate hold sends on release.
  if (heldFor >= 450 && store.get()?.operation.state === "recording") {
    await handle(await commands.stopAndSend());
  }
});

clearButton.addEventListener("click", () => {
  const target = store.get()?.active_target ?? "local";
  clearCopy.textContent = `This removes the saved ${target === "local" ? "Local Ace" : "Server Ace"} transcript.`;
  clearDialog.showModal();
});

clearDialog.addEventListener("close", async () => {
  if (clearDialog.returnValue !== "confirm") return;
  const target = store.get()?.active_target;
  if (target) await handle(await commands.clearConversation(target));
});
