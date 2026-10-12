import unittest

from ace_app.widgets.validation import WidgetValidationError, validate_widget_payload


class WidgetValidationTests(unittest.TestCase):
    def test_accepts_exact_protocol_v1_shape_without_rewriting_html(self):
        html = "<script>window.value = 1</script>"
        value = validate_widget_payload({"id": "daily-news_1", "widget": html})
        self.assertEqual((value.id, value.html), ("daily-news_1", html))

    def test_rejects_extra_missing_and_invalid_fields(self):
        invalid = [
            {},
            {"id": "a", "widget": "x", "version": 1},
            {"id": " spaces ", "widget": "x"},
            {"id": "a", "widget": ""},
            {"id": "a", "widget": "x\x00y"},
            {"id": "a", "widget": 3},
            ["a", "x"],
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(WidgetValidationError):
                validate_widget_payload(payload)

    def test_id_boundary_and_utf8_byte_limit(self):
        validate_widget_payload({"id": "a" * 64, "widget": "x"})
        with self.assertRaises(WidgetValidationError):
            validate_widget_payload({"id": "a" * 65, "widget": "x"})
        with self.assertRaises(WidgetValidationError) as raised:
            validate_widget_payload({"id": "a", "widget": "éé"}, max_widget_bytes=3)
        self.assertEqual(raised.exception.status, 413)


if __name__ == "__main__":
    unittest.main()
