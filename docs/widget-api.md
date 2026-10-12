# Local widget callback API

Ace App opens a session-only HTTP listener on a random `127.0.0.1` port. The
listener is not a general web server and is never exposed on a LAN interface.
Local Ace discovers it from headers on each audio request:

```http
X-Ace-Widget-Callback: http://127.0.0.1:<port>/api/widgets
X-Ace-Widget-Token: <random-per-launch-token>
X-Ace-Widget-Protocol: 1
```

Local Ace should treat these headers as optional and retain their values only
for the lifetime of the current Ace App process. They are deliberately absent
from Server Ace requests.

## Create or replace

Send JSON to the callback URL with the supplied bearer token:

```bash
curl "$ACE_WIDGET_CALLBACK" \
  -H "Authorization: Bearer $ACE_WIDGET_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"id":"daily-news","widget":"<article><h2>Today</h2></article>"}'
```

The protocol-1 body must contain exactly:

- `id`: 1–64 ASCII letters, digits, dots, underscores, or hyphens, beginning
  with a letter or digit;
- `widget`: a non-empty UTF-8 HTML string without NUL characters.

The default maximum body is 256 KiB. A new ID returns `201 Created`; replacing
an existing ID returns `200 OK` and keeps its workspace position and creation
time.

```json
{"id":"daily-news","status":"created","revision":1}
```

Errors use safe JSON messages and return `400`, `401`, `404`, `413`, `415`, or
`503` as appropriate. Responses never echo widget HTML or credentials. `GET`,
agent-facing `DELETE`, CORS, and directory serving are not supported.

Widgets are held only in memory. Clearing an Ace conversation does not remove
them; closing Ace App does. The renderer executes widget scripts only inside a
sandboxed iframe with network, native bridge, parent DOM, permissions, forms,
popups, downloads, persistent storage, and top-level navigation restricted.

