# Ace App Vision and Widget Architecture

## Status

This document defines the intended direction for Ace App. It is a design and
implementation guide, not a description of functionality that already exists.

The first milestone is a locally running desktop application that can use
either Local Ace or Server Ace. The longer-term deployment target is a
server-hosted Ace environment, including the application services.

## Product vision

Ace App should be an interactive visual environment for an AI agent, not only a
voice client or transcript viewer.

The user can continue speaking to Ace, but Ace can also create visual,
interactive responses. For example, when asked for the day's top three news
stories, Ace could speak a short summary and display an HTML news widget with
headlines, sources, expandable summaries, and actions.

The agent should be able to customize the workspace through widgets while the
application remains responsible for:

- desktop window and application lifecycle;
- audio recording and submission;
- selecting Local Ace or Server Ace in the UI;
- conversation history;
- receiving, validating, and rendering widgets;
- widget placement and lifecycle;
- isolation between agent-supplied HTML and privileged app capabilities;
- clear feedback when an agent or widget connection is unavailable.

Ace App is a desktop application. Its interface will use HTML, CSS, and
JavaScript, but it will run inside an application-owned desktop window rather
than being presented as a normal website in a browser tab.

## Confirmed product decisions

- Replace the Tkinter interface with a fully HTML-based desktop interface.
- Keep the existing Python capabilities where practical.
- Initially run the application on the user's PC.
- Allow the user to select Local Ace or Server Ace from the visible UI.
- Do not require a keybind for target selection.
- Accept agent widgets as HTML stored in a JSON string.
- Give widgets IDs so they can be addressed after creation.
- Keep a renderer-owned in-memory list of the widgets currently on screen.
- Append new widgets by default.
- Permit later widget updates and removal by ID.
- Do not remove widgets when a conversation is cleared.
- Do not persist widgets across application restarts.
- Permit JavaScript inside widgets for interaction.
- Isolate widgets from the filesystem, OS, secrets, and privileged application
  APIs.
- Block widget-originated external network requests initially.

## Current application

The current application is a small Python/Tkinter program with five main
parts:

| Component | Current responsibility | Planned direction |
| --- | --- | --- |
| `app.py` | Tkinter window, UI state, orchestration | Split into a Python application host and an HTML frontend |
| `api.py` | Sends audio and clear requests to Ace | Retain as the outbound Ace client; add widget transport/ingestion components |
| `audio.py` | Records WAV audio with PipeWire | Retain behind a controlled frontend command |
| `hotkeys.py` | F9 recording and F10 target switching | Make hotkeys optional; all essential actions must exist in the UI |
| `history.py` | Persists local/server conversation history | Retain, then expose through a narrow frontend bridge |

The current API sends audio to `POST /api/audio` and clears the selected Ace
conversation with `DELETE /api/conversation`. It stores local and server
history separately. It does not currently have an HTML renderer, widget model,
inbound HTTP service, event channel, logs view, or desktop web shell.

## Proposed application architecture

### Desktop shell

Use a native desktop window backed by an embedded browser engine. The first
implementation should evaluate `pywebview`, because it lets the project retain
its Python application core while replacing Tkinter with an HTML/CSS/JavaScript
interface. On Linux, the packaged runtime must include and validate the
appropriate GTK/WebKit dependencies.

The frontend should be bundled with the application and loaded from local
assets. It should not depend on a public web server to draw its interface.

The frontend and Python host have separate responsibilities:

```text
+---------------------------------------------------------+
| Ace desktop window                                      |
|                                                         |
|  HTML application shell                                 |
|  - target selector                                      |
|  - record/send controls                                 |
|  - transcript                                           |
|  - widget workspace                                     |
|  - status and errors                                    |
+--------------------------+------------------------------+
                           | narrow, validated app bridge
+--------------------------+------------------------------+
| Python application host                                 |
|  - audio recorder        - conversation history         |
|  - Ace API clients       - widget store                 |
|  - configuration         - widget ingestion/transport   |
+--------------------------+------------------------------+
                           |
             Local Ace or Server Ace
```

This boundary is important: the application shell may call explicitly exposed
Python commands, but an individual agent widget may not access that bridge.

### Frontend layout

The initial interface should have these regions:

1. **Application header**
   - Local Ace / Server Ace selector.
   - Connection and activity state.
   - Settings entry point.
2. **Conversation area**
   - User and Ace turns.
   - Recording control available directly in the UI.
   - Clear-conversation action.
3. **Widget workspace**
   - Zero or more widget containers managed by the renderer.
   - Empty state when no widgets exist.
   - App-owned controls to dismiss a widget.
4. **Status/error surface**
   - Recording, sending, reconnecting, validation, and rendering failures.

The first layout may use a conversation column beside a larger widget
workspace. It should later support responsive layouts and workspace modes
without changing the widget ingestion contract.

## Widget contract

### Create or replace a widget

The initial canonical payload is:

```json
{
  "id": "daily-news",
  "widget": "<section class=\"news\">...</section>"
}
```

Fields:

- `id`: required non-empty string identifying the widget. The app should
  enforce a length limit and a conservative character set. Sending an existing
  ID replaces that widget's content in place.
- `widget`: required non-empty string containing the widget HTML. The app
  should enforce a configurable payload-size limit.

The transport endpoint is initially specified as:

```text
POST /api/widgets
Content-Type: application/json
```

A successful create should return `201 Created`; replacement of an existing ID
should return `200 OK`. A response can include normalized metadata:

```json
{
  "id": "daily-news",
  "status": "created"
}
```

Expected errors include malformed JSON, a missing or invalid ID, missing HTML,
an oversized payload, failed authentication, and an unavailable renderer.

### Future lifecycle operations

The model and renderer should be designed to support these operations even if
only create/replace is implemented in the first milestone:

```text
DELETE /api/widgets/{id}       remove one widget
DELETE /api/widgets            remove every widget in the current app session
GET    /api/widgets            inspect current widget metadata for diagnostics
```

These operations concern visual workspace state. They are deliberately
independent of `DELETE /api/conversation`.

### Widget model

The Python host owns the authoritative, in-memory widget collection. A widget
record should initially contain:

```text
id
html
created_at
updated_at
source_target     local or server
```

The renderer receives a serializable view of this collection. Widget records
are discarded when the application process exits. They must not be added to
conversation history or written to the history JSON file.

## Widget renderer

The renderer is an application-owned frontend module, not raw HTML inserted
directly into the application's main document.

Its responsibilities are:

- maintain the ordered on-screen widget list;
- add a widget when a new ID arrives;
- update a widget in place when an existing ID arrives;
- remove widgets without affecting conversation history;
- give every widget an app-owned frame, loading state, and error state;
- choose initial placement and sizing;
- preserve application navigation and controls regardless of widget content;
- report render failures without crashing the desktop window.

Each widget should render in a sandboxed iframe or equivalent isolated web
context. Injecting agent HTML with `innerHTML` into the main application DOM is
not acceptable because it would allow widget CSS and JavaScript to control the
entire app.

For the initial release, widget ordering is insertion order. Replacing a widget
keeps its existing position. User-driven rearranging, resizing, pinning, and
multiple workspaces can be designed later.

## Security boundary

Agent-generated HTML is active, untrusted content even when the agent itself is
trusted. A malformed prompt, tool result, or third-party data source could
otherwise produce unsafe markup.

Initial widget restrictions:

- no access to the Python/native application bridge;
- no access to conversation or authentication tokens;
- no filesystem, clipboard, microphone, camera, or OS access;
- no top-level navigation or pop-up windows;
- no external network requests;
- no ability to modify the parent application's DOM or styles;
- no persistence through local storage, IndexedDB, or service workers;
- scripts run only within the isolated widget context;
- links require an explicit app-controlled policy before opening externally.

The app should apply an iframe sandbox and a restrictive Content Security
Policy. The exact allowances must be tested against the selected desktop
webview engine. Sanitizing HTML alone is not a substitute for runtime
isolation.

Future widget-to-app interaction should use a versioned message protocol with
an explicit allowlist of actions. Widgets must never receive direct access to
the general desktop bridge.

## Widget delivery and network topology

There are two separate directions of communication:

1. The desktop app sends audio and conversation commands to the selected Ace.
2. Ace sends widget events back to the desktop app.

For Local Ace, the desktop host can expose `POST /api/widgets` on a loopback
address. The local agent can call it directly.

Server Ace cannot generally call an HTTP endpoint bound to the user's PC due
to NAT, firewalls, and changing addresses. The remote configuration must not
require exposing an unauthenticated desktop port to the internet. The preferred
long-term design is:

- Ace Server accepts widget tool calls through its server-side widget API.
- The desktop app opens an authenticated outbound WebSocket or Server-Sent
  Events connection to Ace Server.
- Ace Server publishes widget events over that connection.
- The desktop app passes every incoming event through the same validation and
  in-memory widget store used by the local `POST /api/widgets` endpoint.

This gives the application one internal widget-ingestion contract while
allowing different transports:

```text
Local Ace  -> loopback POST ----+
                                +-> validate -> widget store -> renderer
Server Ace -> outbound stream --+
```

The first local milestone can implement the loopback endpoint. Server delivery
requires a corresponding authenticated event endpoint in Ace Server and should
be treated as its own integration milestone.

When the whole environment later runs on a server, the same frontend and
widget protocol can be reused. Deployment should still preserve an app-like
shell, authenticated sessions, and widget isolation rather than exposing the
renderer as an unrestricted public webpage.

## Configuration

Existing Local Ace and Server Ace URL/token configuration should remain
supported. The new app will also need configuration for:

- selected target;
- local widget-listener bind address and port;
- local widget API token or per-session secret;
- server widget-stream URL;
- server stream authentication;
- maximum widget payload size;
- development diagnostics.

The target selector belongs in the UI and should be disabled while an audio
request is in progress. Hotkeys may remain optional conveniences, but no core
feature may depend exclusively on a global keybind.

The local widget listener should bind to `127.0.0.1` by default. Binding to a
LAN or public interface must require explicit configuration and authentication.

## State and lifecycle rules

- The app starts with an empty widget workspace.
- Creating a new widget ID appends it to the workspace.
- Sending an existing widget ID replaces it in place.
- Removing a widget does not affect Ace's conversation.
- Clearing Ace's conversation does not remove any widgets.
- Switching Local Ace / Server Ace changes the destination of future audio and
  conversation commands.
- Each widget records which target produced it.
- Widgets remain visible when switching targets unless the user filters them.
- Closing or restarting the app discards every widget.
- Conversation history is session-only and is discarded independently of widgets.

## Implementation phases

### Phase 1: desktop web shell

- Establish the Python host plus HTML frontend structure.
- Recreate current conversation history and status UI.
- Add visible record/send and Local Ace / Server Ace controls.
- Retain existing audio and API client behavior while making history session-only.
- Make global hotkeys optional.
- Package local frontend assets with the application.

Exit condition: the current text-and-audio workflow works without Tkinter and
without requiring F9 or F10.

### Phase 2: local widget foundation

- Define typed widget records and an in-memory widget store.
- Add the loopback `POST /api/widgets` endpoint.
- Validate ID, content type, payload shape, size, and authentication.
- Add the frontend widget workspace and renderer.
- Render each widget in an isolated context.
- Support create, replace, and user dismissal.
- Ensure conversation clearing and app target switching do not remove widgets.

Exit condition: Local Ace can create and update an interactive session-only
HTML widget without gaining privileged application access.

### Phase 3: server delivery

- Define the authenticated server widget-event protocol.
- Add reconnecting WebSocket or SSE transport to the desktop host.
- Route remote and local widget messages through identical validation.
- Surface connection state and delivery failures in the UI.
- Test target attribution and reconnection behavior.

Exit condition: Server Ace can deliver widgets without an inbound public port
on the user's PC.

### Phase 4: workspace capabilities

- Add rearranging and resizing.
- Add widget-focused and split-screen layouts.
- Define a safe, versioned widget message protocol.
- Add app-approved actions and richer accessibility behavior.
- Add a diagnostics/log view for transport and rendering events.

## Testing requirements

The widget work needs tests at several boundaries:

- payload validation and size limits;
- create-versus-replace behavior;
- removal and ordering;
- session-only lifecycle across restart;
- independence from conversation clearing;
- Local Ace / Server Ace attribution;
- unauthorized local API requests;
- iframe isolation and blocked bridge access;
- blocked external requests and navigation;
- malformed HTML and JavaScript failures;
- frontend rendering and user dismissal;
- remote stream reconnect and duplicate event handling;
- end-to-end delivery from a fake agent to the rendered widget.

## First milestone acceptance example

Given an empty workspace, Local Ace sends:

```json
{
  "id": "daily-news",
  "widget": "<article><h2>Today's headlines</h2><button onclick=\"this.nextElementSibling.hidden = false\">Show stories</button><ol hidden><li>Story one</li><li>Story two</li><li>Story three</li></ol></article>"
}
```

The application should:

1. authenticate and validate the request;
2. add `daily-news` to its in-memory widget collection;
3. display it in an isolated frame in the widget workspace;
4. allow the button interaction inside that frame;
5. keep all app controls usable;
6. keep the widget after a conversation clear;
7. discard the widget when the application closes.

That behavior establishes the foundation for the broader agent-controlled
interactive environment.
