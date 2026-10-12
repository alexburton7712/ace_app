from __future__ import annotations

import unittest


class DesktopImportTests(unittest.TestCase):
    def test_window_module_imports_without_optional_qt_runtime(self):
        from ace_app.desktop import window

        self.assertTrue(hasattr(window, "AceWindow"))
        if not window.QT_AVAILABLE:
            with self.assertRaisesRegex(RuntimeError, "PySide6"):
                window.AceWindow(object())


if __name__ == "__main__":
    unittest.main()
