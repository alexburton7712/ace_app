import unittest

from ace_app.config import AppConfig, ConfigError


class AppConfigTests(unittest.TestCase):
    def test_target_tokens_override_shared_token_and_repr_is_safe(self):
        config = AppConfig.from_env(
            {
                "ACE_TOKEN": "shared-secret",
                "LOCAL_ACE_TOKEN": "local-secret",
                "SERVER_ACE_URL": "https://ace.example.test/",
            }
        )

        self.assertEqual(config.local_ace_token, "local-secret")
        self.assertEqual(config.server_ace_token, "shared-secret")
        self.assertEqual(config.server_ace_url, "https://ace.example.test")
        rendered = repr(config)
        self.assertNotIn("local-secret", rendered)
        self.assertNotIn("shared-secret", rendered)
        self.assertIn("<redacted>", rendered)

    def test_defaults_are_local_safe(self):
        config = AppConfig.from_env({})
        self.assertEqual(config.active_target, "local")
        self.assertEqual(config.widget_bind_address, "127.0.0.1")
        self.assertEqual(config.widget_max_body_bytes, 256 * 1024)
        self.assertFalse(config.hotkeys_enabled)

    def test_rejects_public_widget_bind(self):
        with self.assertRaises(ConfigError):
            AppConfig.from_env({"ACE_WIDGET_BIND": "0.0.0.0"})

    def test_rejects_url_credentials(self):
        with self.assertRaises(ConfigError):
            AppConfig.from_env({"LOCAL_ACE_URL": "https://user:secret@example.test"})


if __name__ == "__main__":
    unittest.main()
