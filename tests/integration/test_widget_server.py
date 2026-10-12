import http.client
import json
import socket
import unittest

from ace_app.widgets.local_server import LoopbackWidgetServer
from ace_app.widgets.store import WidgetStore


class WidgetServerTests(unittest.TestCase):
    def setUp(self):
        self.store = WidgetStore()
        self.server = LoopbackWidgetServer(self.store, max_body_bytes=512, socket_timeout=1).start()

    def tearDown(self):
        self.server.stop()

    def request(self, method="POST", path="/api/widgets", body=b"", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=2)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        value = response.read()
        result = (response.status, dict(response.getheaders()), value)
        connection.close()
        return result

    def authorized_headers(self, body):
        return {
            "Authorization": f"Bearer {self.server.token}",
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }

    def test_create_replace_and_callback_metadata(self):
        body = json.dumps({"id": "news", "widget": "<p>one</p>"}).encode()
        status, headers, response = self.request(body=body, headers=self.authorized_headers(body))
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(response)["status"], "created")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Server", headers)
        body = json.dumps({"id": "news", "widget": "<p>two</p>"}).encode()
        status, _, response = self.request(body=body, headers=self.authorized_headers(body))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response), {"id": "news", "status": "replaced", "revision": 2})
        self.assertEqual(self.store.get("news").html, "<p>two</p>")
        self.assertEqual(self.server.callback_headers["X-Ace-Widget-Protocol"], "1")

    def test_rejects_auth_media_shape_size_and_unknown_routes(self):
        body = b'{}'
        base = {"Content-Type": "application/json", "Content-Length": "2"}
        self.assertEqual(self.request(body=body, headers=base)[0], 401)
        headers = self.authorized_headers(body)
        headers["Content-Type"] = "text/plain"
        self.assertEqual(self.request(body=body, headers=headers)[0], 415)
        headers = self.authorized_headers(body)
        self.assertEqual(self.request(body=body, headers=headers)[0], 400)
        oversized = b"x" * 513
        self.assertEqual(self.request(body=oversized, headers=self.authorized_headers(oversized))[0], 413)
        self.assertEqual(self.request(method="GET", path="/api/widgets")[0], 404)
        self.assertEqual(self.request(path="/other")[0], 404)

    def test_invalid_length_and_duplicate_keys_are_bad_requests(self):
        raw = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        raw.sendall(
            b"POST /api/widgets HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            + f"Authorization: Bearer {self.server.token}\r\n".encode()
            + b"Content-Type: application/json\r\nContent-Length: nope\r\nConnection: close\r\n\r\n"
        )
        self.assertIn(b" 400 ", raw.recv(1024))
        raw.close()

        body = b'{"id":"a","id":"b","widget":"x"}'
        self.assertEqual(self.request(body=body, headers=self.authorized_headers(body))[0], 400)

    def test_unavailable_and_clean_shutdown(self):
        self.server.stop()
        unavailable = LoopbackWidgetServer(
            self.store, renderer_available=lambda: False, socket_timeout=1
        ).start()
        self.server = unavailable
        body = b'{"id":"a","widget":"x"}'
        self.assertEqual(self.request(body=body, headers=self.authorized_headers(body))[0], 503)
        port = self.server.port
        self.server.stop()
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=0.2)


if __name__ == "__main__":
    unittest.main()
