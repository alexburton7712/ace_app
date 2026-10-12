# Ace App Rewrite Implementation Plan

## 1. Goal

Replace the current Tkinter application with a new desktop application whose
interface is HTML, CSS, and JavaScript while preserving the useful Ace workflow:

- record a WAV voice message;
- send it to either Local Ace or Server Ace;
- show the recognized user text and Ace's response;
- keep separate session-only conversation transcripts for both targets;
- clear the selected agent's conversation;
- optionally retain the F9 push-to-talk and F10 target-switch shortcuts;
- receive, display, update, and remove interactive widgets produced by Ace.

This is a rewrite, not an incremental reskin. Build the new package beside the
legacy files, prove feature parity, then delete the legacy entry point and
modules. Preserve external contracts, not the current internal structure.

The first shippable release is Linux-first and local-first. Server widgets are a
separate integration milestone because they require support from Ace Server.

## 2. Decisions to make up front

### 2.1 Desktop runtime: PySide6 with Qt WebEngine

Use `PySide6.QtWebEngineWidgets.QWebEngineView` as the application window.
Do not use a normal browser tab and do not expose the frontend on a public
interface.

`pywebview` is attractive for a quick shell, but the product promises that
arbitrary widget JavaScript cannot use the network or native bridge. Qt
WebEngine is the stronger fit because it provides all of the following at the
host boundary:

- request interception and blocking before requests reach Chromium's network
  stack;
- explicit denial of downloads, new windows, navigation, and web permissions;
- an off-the-record browser profile;
- a narrow Qt WebChannel bridge;
- bundled `qrc` assets that do not need a public or LAN-visible web server.

Treat this choice as provisional until the security spike in Phase 0 passes on
the supported Linux distribution. If Qt WebEngine cannot pass every isolation
test, stop before building the full UI and evaluate a separate renderer process.
Do not weaken the widget restrictions to make a chosen shell work.

### 2.2 Frontend: TypeScript without a component framework

Use TypeScript, Vite, semantic HTML, and CSS. The interface is small enough that
React/Vue would add lifecycle and packaging complexity without providing much
value. Split behavior into small modules for the bridge, state store,
conversation rendering, widget rendering, and notifications.

No frontend asset may come from a CDN. Fonts, icons, CSS, and JavaScript must be
bundled with the application.

### 2.3 Native bridge: narrow and capability-protected

Expose exactly one `AppBridge` object to the trusted top-level application page.
Every callable method must require a random 256-bit per-process capability as
its first argument. Inject that capability into a closure in the main frame
after the page loads; never place it in HTML, a DOM attribute, a URL, storage, a
log, or widget content.

The bridge exposes commands only:

```text
get_snapshot(capability)
select_target(capability, target)
start_recording(capability)
stop_and_send(capability)
clear_conversation(capability, target)
dismiss_widget(capability, widget_id)
```

Return JSON-compatible result envelopes rather than uncaught Python exceptions:

```json
{"ok": true, "value": {}}
{"ok": false, "error": {"code": "busy", "message": "Ace is already processing a request"}}
```

Do not expose the Ace clients, filesystem paths, tokens, subprocess APIs, or a
generic `execute`, `read_file`, `fetch`, or `evaluate` method. Send asynchronous
state changes to a single known function in the main frame with
`QWebEnginePage.runJavaScript`; do not broadcast native objects or Qt signals to
untrusted frames.

### 2.4 State ownership

Python is authoritative for:

- selected target;
- operation state;
- recording ownership;
- conversation history;
- agent clients and credentials;
- widget records and ordering;
- widget listener and server-stream status;
- errors that affect native work.

The frontend owns only ephemeral presentation state such as the open settings
panel, the selected workspace mode, and scroll position. On load or reload it
must rebuild itself from `get_snapshot`.

## 3. Target architecture

```text
Qt desktop process
|
+-- QWebEngineView (trusted bundled application UI)
|   |-- header, target selector, status
|   |-- conversation and recording controls
|   `-- app-owned widget frames
|       `-- sandboxed untrusted HTML/JS (one iframe per widget)
|
+-- ApplicationController (single authority for app state)
|   |-- AudioService
|   |-- AceClient[local/server]
|   |-- HistoryRepository
|   `-- WidgetStore
|
+-- LoopbackWidgetServer (127.0.0.1, random available port)
|   `-- authenticated POST /api/widgets for Local Ace
|
`-- ServerWidgetStream (outbound authenticated SSE, later milestone)
    `-- events from Server Ace
```

All state mutations from worker threads must be delivered to the Qt main thread
through queued signals. The frontend must never mutate Python-owned state
optimistically; it may show a pending state, but it reconciles with the next
authoritative snapshot/event.

## 4. Proposed repository layout

```text
ace_app/
  __init__.py
  __main__.py                 # python -m ace_app
  bootstrap.py                # config, dependencies, startup/shutdown order
  controller.py               # state machine and use-case orchestration
  models.py                   # typed snapshots, operations, errors
  config.py                   # validated environment/settings
  services/
    ace_client.py             # POST audio, DELETE conversation
    audio.py                  # pw-record lifecycle
    history.py                # atomic persistent histories
    hotkeys.py                # optional evdev adapter
  widgets/
    models.py                 # Widget and WidgetEvent
    validation.py             # shared validation for every transport
    store.py                  # thread-safe ordered in-memory collection
    local_server.py           # loopback POST endpoint
    server_stream.py          # authenticated SSE client
  desktop/
    window.py                 # QWebEngineView and lifecycle
    bridge.py                 # capability-checked command surface
    request_policy.py         # URL/network/permission enforcement
    resources.qrc
  ui/
    src/
      index.html
      main.ts
      bridge.ts
      state.ts
      conversation.ts
      widgets.ts
      notifications.ts
      styles.css
    package.json
    vite.config.ts
tests/
  unit/
  integration/
  security/
  e2e/
docs/
  agent-api.md
  widget-api.md
  server-widget-stream.md
```

Keep `APP_VISION.md` as the product intent and this file as the build plan. Once
the rewrite passes parity, remove the root-level `app.py`, `api.py`, `audio.py`,
`history.py`, and `hotkeys.py` rather than maintaining two implementations.

## 5. Preserve the existing Ace interaction contract

### Audio

Continue sending:

```text
POST {base_url}/api/audio
Authorization: Bearer <target token>  # when configured
multipart field: file=(clip.wav, <bytes>, audio/wav)
timeout: 120 seconds
```

Continue accepting a non-empty `response`, with temporary `text` and `message`
aliases, and optional `transcription` with the `user_transcript` alias. Preserve
the fallback text `Voice message (transcript unavailable)`.

For Local Ace only, add these request headers so the agent can discover the
per-launch widget callback without a manually synchronized port:

```text
X-Ace-Widget-Callback: http://127.0.0.1:<port>/api/widgets
X-Ace-Widget-Token: <random per-launch local-widget token>
X-Ace-Widget-Protocol: 1
```

Never send the local callback or its token to Server Ace. Local Ace may retain
the callback only for the life of the app session. Log header names, but never
their values. Document this extension in `docs/agent-api.md` and update Local
Ace to treat the headers as optional so older clients remain compatible.

### Clear conversation

Continue sending `DELETE {base_url}/api/conversation` with the selected target's
bearer token. Capture the target in the operation object before starting the
worker. Always clear that target's local session transcript; if Ace cannot
reset its remote context, report that separately. Clearing a conversation must
not touch widgets.

### Session-only history

Keep transcripts in memory, separated into `local` and `server` partitions.
Never load or write conversation content on disk. Remove the legacy history
file on upgrade so an old transcript cannot reappear.

The “newest 10 turns are assumed in context” label is presentation metadata,
not a claim from the server. Define the number in validated configuration and
word it accordingly in the UI.

## 6. Application state and command rules

Use an explicit state machine:

```text
IDLE -> RECORDING -> SENDING -> IDLE
IDLE -> CLEARING -----------> IDLE
any state -> SHUTTING_DOWN
```

Failures return to `IDLE` after publishing a durable error notification. Store
`operation_id`, `kind`, `target`, and `started_at` for every non-idle operation.
The target selector and clear action are disabled in `RECORDING`, `SENDING`, and
`CLEARING`. The stop-recording action is enabled only in `RECORDING`.

The snapshot returned to the UI should be versioned:

```json
{
  "schema_version": 1,
  "revision": 42,
  "active_target": "local",
  "operation": {"state": "idle"},
  "history": {"turns": [], "assumed_context_turns": 10},
  "widgets": [],
  "connections": {
    "local_widget_listener": "connected",
    "server_widget_stream": "not_configured",
    "hotkeys": "disabled"
  },
  "notices": []
}
```

Increment `revision` for every externally visible state change. The frontend
must ignore an event or snapshot older than the latest revision it has applied.
This prevents late worker completions from visually rolling state backward.

## 7. Widget model and validation

Use one internal ingestion function for loopback and server-stream events:

```python
ingest_widget(source_target, untrusted_payload) -> IngestResult
```

Never accept `source_target` from widget JSON. The authenticated transport sets
it: the loopback token maps to `local`; the server stream maps to `server`.

Initial record:

```text
id: str
html: str
source_target: Literal["local", "server"]
created_at: UTC datetime
updated_at: UTC datetime
revision: int
```

Validation rules:

- require `Content-Type: application/json` for HTTP ingestion;
- reject a missing or invalid `Content-Length` before reading a body;
- default maximum body size: 256 KiB, configurable downward or upward within a
  hard safety ceiling;
- require an object containing only `id` and `widget` in protocol version 1;
- require `id` to match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`;
- require `widget` to be a non-empty UTF-8 string;
- reject embedded NUL characters;
- do not rewrite or “repair” agent HTML in the store;
- use constant-time comparison for bearer tokens;
- return safe errors that never echo HTML or secrets.

The `WidgetStore` is ordered by first insertion. Upserting an existing ID
changes `html`, `updated_at`, and `revision` but retains `created_at` and list
position. Dismissal removes the record. Conversation clear and target switching
do not call the widget store. The store never writes widgets to disk.

## 8. Local widget endpoint

Start `ThreadingHTTPServer` on `127.0.0.1` and port `0` before constructing Ace
clients; read the assigned port and generate the callback headers. Use a custom
handler with no directory serving and no permissive CORS behavior.

```text
POST /api/widgets
Authorization: Bearer <per-launch token>
Content-Type: application/json
```

Responses:

```text
201 {"id":"daily-news","status":"created","revision":1}
200 {"id":"daily-news","status":"replaced","revision":2}
400 malformed JSON or shape
401 missing/invalid token
404 every unknown path
413 body too large
415 wrong content type/encoding
503 application is shutting down or renderer unavailable
```

Read with a socket timeout, cap body bytes independently of `Content-Length`,
and limit concurrent handler threads. Set `Cache-Control: no-store` and do not
include the server implementation in response headers.

Deletion and listing are application-control operations, not agent privileges
in the first release. The visible dismiss button calls the native bridge. Add
agent-facing `DELETE`/`GET` only when their authorization and use cases are
defined.

## 9. Widget rendering and isolation

The renderer creates an app-owned card containing title/target metadata, error
state, and dismiss control. Only the inner iframe is agent controlled.

For every create or replacement:

1. Build a complete HTML document from the stored HTML.
2. Put a restrictive CSP before the supplied content.
3. Create a new iframe rather than mutating the old document.
4. Set `sandbox="allow-scripts"` and `referrerpolicy="no-referrer"`.
5. Do not add `allow-same-origin`, `allow-forms`, `allow-popups`,
   `allow-downloads`, `allow-modals`, or navigation allowances.
6. Apply a load timeout and show an app-owned error without removing other
   widgets.

Start with this CSP and tighten it if engine tests permit:

```text
default-src 'none';
script-src 'unsafe-inline';
style-src 'unsafe-inline';
img-src data: blob:;
font-src data:;
media-src 'none';
connect-src 'none';
object-src 'none';
frame-src 'none';
worker-src 'none';
form-action 'none';
base-uri 'none'
```

The CSP is defense in depth. `QWebEngineUrlRequestInterceptor` is the
authoritative egress control:

- allow the exact bundled top-level UI document and its known bundled assets;
- allow the iframe's initial `about:srcdoc`/data document and in-memory
  `data:`/`blob:` resources needed by the policy;
- block every `http`, `https`, `ws`, `wss`, `ftp`, and `file` request made by
  web content;
- block widget attempts to load bundled `qrc` resources, including
  `qwebchannel.js`;
- block all downloads and all top-level navigation away from the application;
- reject new-window and permission requests;
- use an off-the-record profile with memory-only cache and no persistent
  cookies or storage.

The Python Ace client and server stream are native requests and are not routed
through the web engine, so blanket web-content network blocking does not break
agent communication.

Capability checking on `AppBridge` is an additional boundary. A widget must be
unable to perform a command even if it finds a way to instantiate a WebChannel
client. Include an automated test using copied inline WebChannel client code,
not only a test that `qwebchannel.js` failed to load.

Do not claim security completion based only on HTML sanitization. Agent HTML is
allowed to contain scripts, so containment must remain effective for hostile,
not merely malformed, markup.

## 10. Frontend behavior

Use a responsive two-pane layout: conversation on the left and a larger widget
workspace on the right. Collapse to tabs or stacked regions on narrow windows.

Required controls and behavior:

- visible Local Ace / Server Ace selector with keyboard-accessible labels;
- press-and-hold recording button, plus a click/tap mode that clearly changes
  to “Stop and send” for users who cannot hold a pointer button;
- recording timer and explicit recording/sending/clearing states;
- clear-conversation confirmation naming the target and clarifying that widgets
  remain;
- session transcript with context grouping and timestamps;
- widget empty state, app-owned dismiss button, source-target badge, and render
  error state;
- non-modal status notices for recoverable errors, with a details affordance;
- no workflow that requires F9 or F10;
- accessible focus order, visible focus, reduced-motion support, and live-region
  announcements for recording and response completion.

Do not render conversation text as HTML. Set it with `textContent` so an agent's
text response cannot become application markup.

## 11. Optional global hotkeys

Put global hotkeys behind a setting and an adapter. Failure to access evdev must
produce a non-blocking notice rather than an application error. The application
must be fully usable without membership in the Linux `input` group.

F9 retains push-to-talk semantics and ignores key repeat. F10 switches target
only while idle. Both invoke the same controller commands as the visible UI so
there is one state machine and one set of race checks.

## 12. Server widget delivery

Prefer authenticated Server-Sent Events because delivery is server-to-client
only. Run the SSE client in Python, where the existing bearer token can be sent
as a header; do not connect from widget or frontend JavaScript.

Proposed endpoint:

```text
GET {server_base_url}/api/widget-events
Accept: text/event-stream
Authorization: Bearer <server token>
Last-Event-ID: <last processed event id>  # on reconnect
```

Versioned event data:

```json
{
  "version": 1,
  "event_id": "01K...",
  "type": "widget.upsert",
  "widget": {"id": "daily-news", "widget": "<article>...</article>"}
}
```

Initially support `widget.upsert`. Reserve `widget.remove` without enabling it
until desired. Validate the nested widget with the exact same validator as the
local endpoint. Keep a bounded in-memory set of processed event IDs to suppress
duplicates. Reconnect with exponential backoff plus jitter, honor server retry
hints within configured bounds, and expose `connecting`, `connected`,
`reconnecting`, `unauthorized`, and `unavailable` states to the UI.

Audio must continue to work if the stream is absent. The UI should say “Server
widgets unavailable” rather than presenting the entire agent as disconnected.

## 13. Startup and shutdown order

Startup:

1. Parse and validate configuration without printing secrets.
2. Create history, widget store, and controller.
3. Start the loopback widget listener and generate its token.
4. Construct Local/Server Ace clients.
5. Start the server widget stream if configured.
6. Create the off-the-record WebEngine profile, request policy, bridge, and
   window.
7. Load bundled UI assets, inject the bridge capability, and send a snapshot.
8. Start optional hotkeys last.

Shutdown:

1. Enter `SHUTTING_DOWN` and reject new commands/widget posts.
2. Stop accepting local widget requests.
3. Stop the server stream and hotkeys.
4. Terminate and reap an active recorder; ignore late agent responses.
5. Shut down executors with a bounded wait.
6. Clear the in-memory widget store and bridge capability.
7. Destroy the WebEngine profile and window.

Never leave `pw-record`, listener, or worker threads behind after the window
closes.

## 14. Implementation phases

### Phase 0 — isolation and packaging spike

- Create a minimal Qt window with a trusted bundled page and one hostile iframe.
- Implement the capability-checked bridge and request interceptor.
- Prove that the iframe can run inline JavaScript but cannot call the bridge,
  fetch loopback or internet URLs, load remote images/scripts, navigate the top
  level, open a window, download, read `file:` URLs, use storage, or request
  clipboard/microphone/camera access.
- Build a packaged artifact and run it on the oldest supported Linux image with
  no developer tools or source tree present.
- Record supported PySide6/Qt versions and required system libraries.

Exit gate: all hostile-widget tests pass in both development and packaged
builds. Otherwise redesign the renderer boundary before continuing.

### Phase 1 — feature-parity shell

- Create the package, configuration, controller, and typed snapshot.
- Reimplement audio, Ace client, history, and optional hotkeys behind services.
- Build the full HTML interface and bridge commands.
- Preserve the existing `/api/audio` and `/api/conversation` behavior.
- Add unit and controller integration tests.

Exit gate: Local and Server Ace voice conversations, history, clearing, and
optional shortcuts work without Tkinter and without requiring a shortcut.

### Phase 2 — local widgets

- Implement model, validator, ordered store, and loopback listener.
- Add callback discovery headers to Local Ace audio requests.
- Implement widget frames, replacement, dismissal, errors, and empty state.
- Run the full security suite against accepted widget payloads.
- Provide a tiny fake Local Ace fixture and documented `curl` example.

Exit gate: Local Ace can create and replace an interactive widget; it survives
conversation clearing, disappears on app restart, and cannot cross the security
boundary.

### Phase 3 — Server Ace widgets

- Finalize the SSE contract with Ace Server.
- Implement authenticated stream, reconnect, event de-duplication, and status.
- Exercise delivery across disconnect/reconnect and token failure.
- Verify that local and server widgets retain correct target attribution when
  the visible target changes.

Exit gate: Server Ace delivers widgets through an outbound-only connection and
audio remains usable during stream failure.

### Phase 4 — replacement and release

- Package with the pinned Qt runtime/frontend assets.
- Update README and API documents from tested behavior.
- Test that an existing history file is discarded rather than loaded.
- Delete the legacy root modules and Tk dependency.
- Make `python -m ace_app` and the packaged launcher the only supported entry
  points.

Exit gate: clean install, upgrade, uninstall, and restart tests pass; no legacy
implementation remains.

### Phase 5 — later workspace features

Only after the security and delivery foundations are stable, add resizing,
reordering, focused-widget mode, diagnostics, and a versioned allowlisted
widget-to-app message protocol. Do not add direct bridge access to widgets.

## 15. Test plan

### Unit

- configuration precedence and secret redaction;
- Ace URL construction, auth, aliases, timeouts, and safe errors;
- audio subprocess start/stop/discard and invalid WAV handling;
- legacy-history removal, session-only storage, and per-target clear;
- state-machine transitions and busy-command rejection;
- widget ID/body/content-type/size/token validation;
- create versus replace ordering and timestamps;
- event revision and server event de-duplication.

### Integration

- fake Ace receives the exact multipart audio and callback headers;
- local widget POST reaches the store and renderer notification path;
- clear completion applies to the operation's captured target;
- widgets are independent of history clear and target changes;
- listener binds only to loopback by default and stops cleanly;
- SSE reconnect sends `Last-Event-ID` and does not duplicate a widget event.

### Security

Use hostile widgets that attempt:

- `parent.document` and parent CSS modification;
- every bridge method, with and without copied WebChannel setup code;
- `fetch`, XHR, WebSocket, EventSource, beacon, remote image/script/font/media;
- top/frame navigation, popups, downloads, forms, and custom protocols;
- `file:`/`qrc:` reads and path discovery;
- localStorage, IndexedDB, service workers, clipboard, camera, microphone, and
  geolocation;
- CSP escape through malformed head/body markup;
- oversized DOM, infinite loops, repeated dialogs, and exception storms.

Assert both that privileged actions did not happen and that no outbound request
reached a controlled test server. A widget CPU/memory denial of service may
require a later renderer-process boundary; document measured behavior and set a
clear release threshold during Phase 0.

### Frontend and end-to-end

- semantic labels, keyboard navigation, focus restoration, and live regions;
- click/touch recording flow and record cancellation on close;
- transcript escaping and context grouping;
- widget append, in-place position on replacement, dismissal, and error state;
- target selector disabling while busy;
- packaged launch with frontend assets unavailable from the filesystem;
- restart proves widgets and transcript history are gone.

## 16. Definition of done for the first release

The rewrite is complete only when:

- every current agent interaction works from visible controls;
- Local Ace and Server Ace use separate URLs, tokens, and histories;
- all requests capture their target and cannot switch destination mid-flight;
- Local Ace can create and replace session-only interactive widgets;
- widgets cannot access the bridge, filesystem, device permissions, app DOM,
  secrets, external network, top navigation, or persistent storage;
- clearing a conversation leaves widgets intact;
- restarting clears widgets and transcript history;
- failures are visible and recoverable without crashing the window;
- the packaged Linux build passes the same security and parity tests as the
  development build;
- legacy Tkinter code and dependencies have been removed.

Do not combine release completion with workspace resizing, arbitrary
widget-to-app actions, or Server Ace widget streaming. Those are independent
milestones and must not delay replacing the legacy UI once the local secure
foundation is ready.

## 17. Primary technical references

- [Qt WebEngine request interception](https://doc.qt.io/qtforpython-6/overviews/qtwebengine-overview.html)
- [Qt WebEngine URL request information](https://doc.qt.io/qt-6/qwebengineurlrequestinfo.html)
- [Qt WebEngine security considerations](https://doc.qt.io/qt-6/qtwebengine-security.html)
- [Qt WebChannel JavaScript API](https://doc.qt.io/qtforpython-6/overviews/qtwebchannel-javascript.html)
- [HTML iframe sandbox behavior](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe)
- [Content Security Policy sandbox](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/sandbox)
