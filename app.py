from __future__ import annotations

import os
import queue
import threading
from collections.abc import Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError as exc:
    if exc.name == "tkinter":
        raise SystemExit(
            "Ace App needs Python's Tk bindings. On Ubuntu, run: "
            "sudo apt install python3-tk"
        ) from exc
    raise

from api import AceAPIError, AceClient
from audio import AudioRecorder, RecordingError
from history import HistoryStore, Turn
from hotkeys import HotkeyError, HotkeyListener


class AceApp(tk.Tk):
    LLM_CONTEXT_TURNS = 10

    def __init__(
        self,
        clients: dict[str, AceClient] | None = None,
        history_store: HistoryStore | None = None,
    ) -> None:
        super().__init__()
        self.title("Ace App")
        self.geometry("700x480")
        self.minsize(480, 320)
        self.protocol("WM_DELETE_WINDOW", self._close)

        local_url = os.environ.get("LOCAL_ACE_URL", "http://127.0.0.1:8001")
        server_url = os.environ.get("SERVER_ACE_URL", local_url)
        shared_token = os.environ.get("ACE_TOKEN")
        self.clients = clients or {
            "local": AceClient(local_url, os.environ.get("LOCAL_ACE_TOKEN", shared_token)),
            "server": AceClient(server_url, os.environ.get("SERVER_ACE_TOKEN", shared_token)),
        }
        self.active_target = "local"
        self.recording_target: str | None = None
        self.busy = False
        self.recorder = AudioRecorder()
        self.history_store = history_store or HistoryStore()
        self.callbacks: queue.Queue[Callable[[], None]] = queue.Queue()
        self.hotkeys = HotkeyListener(
            lambda: self.callbacks.put(self._start_recording),
            lambda: self.callbacks.put(self._stop_and_send),
            lambda: self.callbacks.put(self._toggle_target),
        )

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame)
        header.pack(fill="x")
        ttk.Label(header, text="Conversation history", font=("TkDefaultFont", 14, "bold")).pack(side="left")
        self.target = tk.StringVar()
        ttk.Label(header, textvariable=self.target, font=("TkDefaultFont", 11, "bold")).pack(side="right")

        response_frame = ttk.Frame(frame)
        response_frame.pack(fill="both", expand=True, pady=(10, 16))
        self.response = tk.Text(response_frame, wrap="word", state="disabled", padx=12, pady=12)
        self.response.tag_configure("section", foreground="#666666", justify="center", spacing1=12, spacing3=8)
        self.response.tag_configure("user", foreground="#1859a9", font=("TkDefaultFont", 10, "bold"), spacing1=8)
        self.response.tag_configure("assistant", foreground="#276b34", font=("TkDefaultFont", 10, "bold"), spacing1=8)
        self.response.tag_configure("body", lmargin1=12, lmargin2=12, spacing3=5)
        scrollbar = ttk.Scrollbar(response_frame, command=self.response.yview)
        self.response.configure(yscrollcommand=scrollbar.set)
        self.response.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status = tk.StringVar(value="Hold F9 to record · F10 switches target")
        footer = ttk.Frame(frame)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        self.clear_button = ttk.Button(
            footer, text="Clear conversation", command=self._clear_conversation
        )
        self.clear_button.pack(side="right")
        self._update_target_label()
        self._render_history()

        self.after(80, self._drain_callbacks)
        self.after(100, self._start_hotkeys)

    def _start_hotkeys(self) -> None:
        try:
            self.hotkeys.start()
        except HotkeyError as exc:
            self._show_error(exc)

    def _toggle_target(self) -> None:
        if self.busy or self.recorder.recording:
            return
        self.active_target = "server" if self.active_target == "local" else "local"
        self._update_target_label()
        self._render_history()
        self.status.set(f"Ready · sending to {self._target_name(self.active_target)}")

    def _start_recording(self) -> None:
        if self.busy or self.recorder.recording:
            return
        self.recording_target = self.active_target
        self.clear_button.configure(state="disabled")
        try:
            self.recorder.start()
        except RecordingError as exc:
            self.recording_target = None
            self.clear_button.configure(state="normal")
            self._show_error(exc)
            return
        self.status.set(f"Recording for {self._target_name(self.recording_target)}… release F9 to send")

    def _stop_and_send(self) -> None:
        if not self.recorder.recording:
            return
        target = self.recording_target or self.active_target
        try:
            wav_data = self.recorder.stop()
        except RecordingError as exc:
            self.recording_target = None
            self._show_error(exc)
            return

        self.recording_target = None
        self.busy = True
        self.status.set(f"Waiting for {self._target_name(target)}…")
        threading.Thread(target=self._send_audio, args=(target, wav_data), daemon=True).start()

    def _clear_conversation(self) -> None:
        if self.busy or self.recorder.recording:
            return
        target = self.active_target
        target_name = self._target_name(target)
        confirmed = messagebox.askyesno(
            "Clear conversation",
            f"Clear the current conversation on {target_name}? This cannot be undone.",
            parent=self,
        )
        if not confirmed:
            return
        self.busy = True
        self.clear_button.configure(state="disabled")
        self.status.set(f"Clearing conversation on {target_name}…")
        threading.Thread(target=self._send_clear, args=(target,), daemon=True).start()

    def _send_clear(self, target: str) -> None:
        try:
            self.clients[target].clear_conversation()
            self.callbacks.put(self._conversation_cleared)
        except Exception as exc:
            self.callbacks.put(lambda exc=exc: self._show_error(exc))

    def _conversation_cleared(self) -> None:
        try:
            self.history_store.clear(self.active_target)
        except OSError as exc:
            self._show_error(exc)
            return
        self._render_history()
        self.busy = False
        self.clear_button.configure(state="normal")
        self.status.set(f"Conversation cleared on {self._target_name(self.active_target)}")

    def _send_audio(self, target: str, wav_data: bytes) -> None:
        try:
            reply = self.clients[target].send_audio(wav_data)
            self.callbacks.put(lambda: self._show_response(target, reply.response, reply.transcription))
        except Exception as exc:
            self.callbacks.put(lambda exc=exc: self._show_error(exc))

    def _show_response(self, target: str, answer: str, transcription: str | None) -> None:
        user_text = transcription or "Voice message (transcript unavailable)"
        try:
            self.history_store.append(target, user_text, answer)
        except OSError as exc:
            self._show_error(exc)
            return
        if target == self.active_target:
            self._render_history()
        self.busy = False
        self.clear_button.configure(state="normal")
        self.status.set("Hold F9 to record · F10 switches target")

    def _render_history(self) -> None:
        turns = self.history_store.turns(self.active_target)
        self.response.configure(state="normal")
        self.response.delete("1.0", "end")
        if not turns:
            self.response.insert("end", "No local conversation history yet.", "section")
        else:
            context_start = max(0, len(turns) - self.LLM_CONTEXT_TURNS)
            if context_start:
                self.response.insert(
                    "end",
                    f"ARCHIVED · {context_start} TURN{'S' if context_start != 1 else ''} NOT IN CURRENT LLM CONTEXT\n",
                    "section",
                )
                for turn in turns[:context_start]:
                    self._render_turn(turn)
            context_count = len(turns) - context_start
            self.response.insert(
                "end",
                f"CURRENT LLM CONTEXT · NEWEST {context_count} OF {self.LLM_CONTEXT_TURNS} TURNS\n",
                "section",
            )
            for turn in turns[context_start:]:
                self._render_turn(turn)
        self.response.configure(state="disabled")
        self.response.see("end")

    def _render_turn(self, turn: Turn) -> None:
        timestamp = turn.timestamp.replace("T", " ").replace("Z", " UTC")
        self.response.insert("end", f"You · {timestamp}\n", "user")
        self.response.insert("end", f"{turn.user_text}\n", "body")
        self.response.insert("end", "Ace\n", "assistant")
        self.response.insert("end", f"{turn.assistant_text}\n", "body")

    def _show_error(self, error: Exception) -> None:
        message = str(error) if isinstance(error, (AceAPIError, RecordingError, HotkeyError, OSError)) else f"Unexpected error: {error}"
        self.busy = False
        self.clear_button.configure(state="normal")
        self.status.set("Error")
        messagebox.showerror("Ace App", message, parent=self)

    def _update_target_label(self) -> None:
        self.target.set(f"Target: {self._target_name(self.active_target)}")

    @staticmethod
    def _target_name(target: str) -> str:
        return "Local Ace" if target == "local" else "Server Ace"

    def _drain_callbacks(self) -> None:
        try:
            while True:
                self.callbacks.get_nowait()()
        except queue.Empty:
            pass
        self.after(80, self._drain_callbacks)

    def _close(self) -> None:
        self.hotkeys.stop()
        self.recorder.discard()
        self.destroy()


if __name__ == "__main__":
    AceApp().mainloop()
