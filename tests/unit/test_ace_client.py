import unittest
from unittest.mock import Mock, patch

from ace_app.services.ace_client import AceAPIError, AceClient


class AceClientTests(unittest.TestCase):
    @patch("ace_app.services.ace_client.requests.post")
    def test_local_audio_includes_callback_discovery_headers(self, post: Mock):
        post.return_value.json.return_value = {"response": "Done"}
        client = AceClient(
            "http://local.test",
            target="local",
            widget_callback_url="http://127.0.0.1:1234/api/widgets",
            widget_callback_token="widget-secret",
        )

        client.send_audio(b"RIFFaudio")

        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["X-Ace-Widget-Protocol"], "1")
        self.assertEqual(headers["X-Ace-Widget-Token"], "widget-secret")

    @patch("ace_app.services.ace_client.requests.post")
    def test_server_never_includes_callback_discovery_headers(self, post: Mock):
        post.return_value.json.return_value = {"text": "Alias", "user_transcript": "Question"}
        client = AceClient(
            "https://server.test",
            target="server",
            token="server-secret",
            widget_callback_url="http://127.0.0.1:1234/api/widgets",
            widget_callback_token="widget-secret",
        )

        reply = client.send_audio(b"RIFFaudio")

        self.assertEqual(reply.transcription, "Question")
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers, {"Authorization": "Bearer server-secret"})

    def test_callback_configuration_must_be_complete(self):
        with self.assertRaises(ValueError):
            AceClient("http://local.test", widget_callback_token="secret")

    def test_request_error_does_not_disclose_secrets(self):
        session = Mock()
        response = Mock(status_code=401)
        session.post.side_effect = __import__("requests").RequestException(
            "token-secret in https://server.test", response=response
        )
        client = AceClient("https://server.test", token="token-secret", session=session)

        with self.assertRaises(AceAPIError) as raised:
            client.send_audio(b"RIFFaudio")

        self.assertNotIn("token-secret", str(raised.exception))
        self.assertEqual(str(raised.exception), "Could not send audio (HTTP 401)")


if __name__ == "__main__":
    unittest.main()
