import unittest
from unittest.mock import Mock, patch

from api import AceAPIError, AceClient


class AceClientTests(unittest.TestCase):
    def test_audio_url(self):
        client = AceClient("http://127.0.0.1:8001/")
        self.assertEqual(client.audio_url, "http://127.0.0.1:8001/api/audio")
        self.assertEqual(client.conversation_url, "http://127.0.0.1:8001/api/conversation")

    @patch("api.requests.post")
    def test_send_audio_returns_agent_response(self, post: Mock):
        response = post.return_value
        response.json.return_value = {"response": "Done", "transcription": "Do the thing"}

        reply = AceClient("http://agent.test").send_audio(b"RIFFaudio")

        self.assertEqual(reply.response, "Done")
        self.assertEqual(reply.transcription, "Do the thing")
        files = post.call_args.kwargs["files"]
        self.assertEqual(files["file"], ("clip.wav", b"RIFFaudio", "audio/wav"))

    @patch("api.requests.post")
    def test_send_audio_rejects_missing_response(self, post: Mock):
        post.return_value.json.return_value = {}
        with self.assertRaises(AceAPIError):
            AceClient("http://agent.test").send_audio(b"RIFFaudio")

    @patch("api.requests.delete")
    def test_clear_conversation_accepts_empty_204_response(self, delete: Mock):
        client = AceClient("http://agent.test", token="secret")

        client.clear_conversation()

        delete.assert_called_once_with(
            "http://agent.test/api/conversation",
            headers={"Authorization": "Bearer secret"},
            timeout=120,
        )
        delete.return_value.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
