# Ace Agent API

Ace App records a WAV clip, uploads it, waits for Ace to finish, and displays
Ace's text response. It can also clear the selected agent's current conversation.

## Endpoint

```text
POST /api/audio
```

The request is `multipart/form-data` with one field:

```text
field name: file
filename: clip.wav
content type: audio/wav
value: WAV file bytes
```

Successful response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "transcription": "Turn on the kitchen light",
  "response": "The kitchen light is now on."
}
```

`response` must be a non-empty string. The client also accepts `text` or
`message` as temporary aliases, but `response` is the canonical field.
`transcription` is optional but recommended so the app can preserve the user's
side of its local conversation history. `user_transcript` is accepted as a
temporary alias.

The request stays open while Ace transcribes the audio, processes the request,
and generates its answer. The client timeout is 120 seconds.

### Optional Local Ace widget callback

Only requests to Local Ace include these per-launch discovery headers:

```http
X-Ace-Widget-Callback: http://127.0.0.1:<random-port>/api/widgets
X-Ace-Widget-Token: <random-per-launch-token>
X-Ace-Widget-Protocol: 1
```

Local Ace may use the callback while the request's Ace App process remains
open. These are optional extensions: an agent without widget support should
ignore them. The token and callback must not be persisted, logged, forwarded
to Server Ace, or reused after the desktop app exits.

The callback accepts an authenticated JSON payload such as:

```json
{
  "id": "daily-news",
  "widget": "<article><h2>Today's headlines</h2></article>"
}
```

See [`docs/widget-api.md`](docs/widget-api.md) for validation and responses.

## Authentication

If a token is configured for the selected target, the app sends:

```http
Authorization: Bearer <token>
```

Use HTTPS for remote agents.

The app has two independently configured base URLs, `LOCAL_ACE_URL` and
`SERVER_ACE_URL`. The visible target control (or optional F10 shortcut) changes
which base URL receives the next `/api/audio` request; the endpoint contract is
otherwise identical for both agents.

## Errors

Return a non-2xx status with a safe JSON message:

```json
{
  "message": "Audio could not be transcribed"
}
```

Useful statuses include `400` for malformed input, `401` for invalid
authentication, `413` for oversized audio, `415` for unsupported audio, and
`500` or `503` for agent failures.

## Clear the current conversation

```text
DELETE /api/conversation
```

Return `204 No Content` after clearing the agent's current conversation. The
request uses the same optional bearer authorization as audio submission. The
operation applies only to the selected Local Ace or Server Ace instance.

No conversation listing, history retrieval, run management, capability
discovery, health check, cancellation, text input, or past-transcript endpoint
is required. Widget delivery is separate from the conversation API.

Ace App keeps the responses it observes in memory for the current app session
and assumes the newest 10 turns are in the model's current context. This does
not require an agent history endpoint.
