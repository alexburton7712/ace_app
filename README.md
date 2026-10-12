# Ace App

Ace App is a Linux-first desktop voice client and interactive workspace for
Local Ace and Server Ace. Its native Python host records audio, keeps separate
session-only conversation transcripts, and accepts session-only HTML widgets;
its interface is a bundled TypeScript application rendered by Qt WebEngine.

The supported application lives in `ace_app/`. The earlier Tkinter
implementation has been removed; `python -m ace_app` is the sole entry point.

## Current implementation

- Visible Local Ace / Server Ace selection, recording, sending, transcript,
  and clear controls. Transcripts exist only for the current app session.
- Explicit `idle → recording → sending/clearing → idle` controller state with
  captured targets and revisioned snapshots.
- Existing `/api/audio` and `/api/conversation` contracts, with separate
  in-memory local/server transcripts.
- Optional F9 push-to-talk and F10 target switching; the app remains fully
  usable without `evdev` access.
- Authenticated loopback widget ingestion, strict validation, ordered in-memory
  storage, replacement, dismissal, and lifecycle independence from history.
- Sandboxed iframe rendering with CSP, WebEngine request interception, a
  capability-protected six-command bridge, and denial of navigation,
  downloads, new windows, and device permissions.

Server widget streaming, packaged-build validation, and live hostile-widget
tests are separate milestones. The client supports server audio and conversation
clearing when Server Ace exposes the documented endpoints; only Server Ace
widget delivery awaits its server-side SSE contract.

## Requirements and setup

- Python 3.10+
- PipeWire and `pw-record`
- Qt WebEngine system libraries supported by PySide6
- Node.js 20+ only when rebuilding frontend assets

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ace_app/ui
npm install
npm run build
cd ../..
```

On Ubuntu, PipeWire recording support is available from `pipewire-bin`. Qt may
also require the distribution's standard XCB/Wayland and multimedia runtime
libraries.

Configure the agents through environment variables:

```bash
LOCAL_ACE_URL=http://127.0.0.1:8001
SERVER_ACE_URL=https://ace.example.com
LOCAL_ACE_TOKEN=optional-local-token
SERVER_ACE_TOKEN=optional-server-token
ACE_HOTKEYS_ENABLED=false
```

`ACE_TOKEN` can provide a shared fallback token. Target-specific tokens take
precedence. Other validated settings include `ACE_TARGET`,
`ACE_REQUEST_TIMEOUT`, `ACE_ASSUMED_CONTEXT_TURNS`, and
`ACE_WIDGET_MAX_BODY_BYTES`. `ACE_HISTORY_PATH` is accepted only to locate and
remove a transcript file created by an older app version.

Run the desktop application with:

```bash
.venv/bin/python -m ace_app
```

Conversation transcripts and widgets are held only in memory and disappear
when the app closes. On first launch, this version removes the legacy
`$XDG_DATA_HOME/ace-app/history.json` file rather than loading it.

## Local widgets

Local audio requests advertise a per-launch callback URL and bearer token.
Local Ace can create or replace a widget by POSTing:

```json
{
  "id": "daily-news",
  "widget": "<article><h2>Today's headlines</h2></article>"
}
```

The token is never sent to Server Ace. See [the widget callback
contract](docs/widget-api.md) and [the agent audio contract](AGENT_API.md).

## Tests

```bash
python3 -m unittest discover -s tests -v
cd ace_app/ui && npm test && npm run build
```

The widget-server integration tests bind a temporary loopback port. Environments
that prohibit socket creation must grant local-loopback access for that suite.

The unit and policy tests do not substitute for running the hostile-widget
suite in a live PySide6 WebEngine and packaged build on the supported Linux
baseline.
