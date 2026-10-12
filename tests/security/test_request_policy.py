from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ace_app.desktop.request_policy import TrustedRequestPolicy


class FakeUrl:
    def __init__(self, value: str):
        self.value = value

    def scheme(self) -> str:
        return self.value.split(":", 1)[0]

    def path(self) -> str:
        if self.value.startswith("qrc:"):
            return self.value[4:]
        return ""

    def toLocalFile(self) -> str:
        return self.value.removeprefix("file://")


class RequestPolicyTests(unittest.TestCase):
    def test_blocks_all_network_egress_schemes(self):
        policy = TrustedRequestPolicy()
        trusted = FakeUrl("qrc:/ace-ui/index.html")
        for scheme in ("http", "https", "ws", "wss", "ftp"):
            with self.subTest(scheme=scheme):
                self.assertFalse(policy.is_allowed(FakeUrl(f"{scheme}://127.0.0.1/secret"), trusted))

    def test_widgets_cannot_load_qrc_but_app_can(self):
        policy = TrustedRequestPolicy()
        asset = FakeUrl("qrc:/ace-ui/assets/main.js")
        self.assertTrue(policy.is_allowed(asset, FakeUrl("qrc:/ace-ui/index.html")))
        self.assertFalse(policy.is_allowed(asset, FakeUrl("about:srcdoc")))
        channel = FakeUrl("qrc:/qtwebchannel/qwebchannel.js")
        self.assertFalse(policy.is_allowed(channel, FakeUrl("about:srcdoc")))
        self.assertTrue(policy.is_allowed(channel, FakeUrl("qrc:/ace-ui/index.html")))

    def test_dev_files_are_scoped_and_widget_file_reads_are_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "dist"
            root.mkdir()
            policy = TrustedRequestPolicy(dev_root=root)
            asset = FakeUrl(f"file://{root / 'assets/main.js'}")
            app = FakeUrl(f"file://{root / 'index.html'}")
            self.assertTrue(policy.is_allowed(asset, app))
            self.assertFalse(policy.is_allowed(asset, FakeUrl("about:srcdoc")))
            self.assertFalse(policy.is_allowed(FakeUrl("file:///etc/passwd"), app))

    def test_srcdoc_and_in_memory_resources_are_admitted_for_csp_to_filter(self):
        policy = TrustedRequestPolicy()
        widget = FakeUrl("about:srcdoc")
        self.assertTrue(policy.is_allowed(widget, FakeUrl("about:blank")))
        self.assertTrue(policy.is_allowed(FakeUrl("data:image/png;base64,AA=="), widget))
        self.assertTrue(policy.is_allowed(FakeUrl("blob:null/id"), widget))
