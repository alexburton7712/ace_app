from __future__ import annotations

import unittest
from pathlib import Path


UI = Path(__file__).parents[2] / "ace_app" / "ui" / "src"


class FrontendContractTests(unittest.TestCase):
    def test_widget_iframe_keeps_opaque_script_only_sandbox(self):
        source = (UI / "widgets.ts").read_text(encoding="utf-8")
        self.assertIn('setAttribute("sandbox", "allow-scripts")', source)
        self.assertNotIn('"allow-same-origin"', source)
        self.assertIn("connect-src 'none'", source)
        self.assertIn("form-action 'none'", source)

    def test_transcript_uses_text_content(self):
        source = (UI / "conversation.ts").read_text(encoding="utf-8")
        self.assertIn("body.textContent = turnText(turn)", source)
        self.assertNotIn("innerHTML", source)

    def test_every_required_command_has_a_frontend_wrapper(self):
        source = (UI / "bridge.ts").read_text(encoding="utf-8")
        for command in (
            "get_snapshot",
            "select_target",
            "start_recording",
            "stop_and_send",
            "clear_conversation",
            "dismiss_widget",
        ):
            with self.subTest(command=command):
                self.assertIn(f'"{command}"', source)
