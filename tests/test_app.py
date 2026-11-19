import os
import unittest
from unittest.mock import Mock, patch

from helpers import APP
from streamlit.testing.v1 import AppTest


class AppTests(unittest.TestCase):
    def open_app(self):
        app = AppTest.from_file(str(APP / "app.py"), default_timeout=15).run()
        self.assertEqual(len(app.exception), 0)
        return app

    @patch("databricks.sdk.WorkspaceClient", side_effect=AssertionError("No authentication in simulation"))
    def test_default_and_supported_simulation_do_not_authenticate(self, workspace):
        app = self.open_app()
        self.assertFalse(app.checkbox[0].value)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("Simulation, not AI", app.text[0].value)
        self.assertIn("E101", app.text[0].value)
        self.assertIn("E104", app.text[0].value)
        workspace.assert_not_called()

    def test_unsupported_and_blank_questions(self):
        app = self.open_app()
        app.text_input[0].set_value("What is the cancellation policy?")
        app.button[0].click().run()
        self.assertIn("only supports", app.text[0].value)
        app.text_input[0].set_value(" ")
        app.button[0].click().run()
        self.assertEqual(len(app.error), 1)
        self.assertEqual(len(app.exception), 0)

    @patch.dict(os.environ, {}, clear=True)
    @patch("databricks.sdk.WorkspaceClient")
    def test_live_toggle_is_not_a_request_and_missing_resource_is_safe(self, workspace):
        app = self.open_app()
        app.checkbox[0].check().run()
        workspace.assert_not_called()
        app.button[0].click().run()
        workspace.assert_not_called()
        self.assertEqual(len(app.error), 1)
        self.assertEqual(len(app.exception), 0)

    @patch.dict(os.environ, {"SERVING_ENDPOINT": "approved-model"})
    @patch("logic.answer_live", return_value="E101: 18. E104: 22.")
    @patch("databricks.sdk.WorkspaceClient")
    def test_explicit_live_submission_once_not_on_rerun(self, workspace, answer):
        app = self.open_app()
        app.checkbox[0].check().run()
        answer.assert_not_called()
        app.button[0].click().run()
        self.assertEqual(app.text[0].value, "E101: 18. E104: 22.")
        answer.assert_called_once()
        workspace.return_value.serving_endpoints.get_open_ai_client.return_value.with_options.assert_called_once_with(
            max_retries=0, timeout=45.0,
        )
        app.run()
        self.assertEqual(answer.call_count, 1)
        app.checkbox[0].uncheck().run()
        self.assertEqual(answer.call_count, 1)
        app.button[0].click().run()
        self.assertIn("Simulation", app.text[0].value)
        self.assertEqual(answer.call_count, 1)

    @patch.dict(os.environ, {"SERVING_ENDPOINT": "approved-model"})
    @patch("logic.answer_live", side_effect=RuntimeError("private request detail"))
    @patch("databricks.sdk.WorkspaceClient")
    def test_provider_error_is_not_displayed(self, workspace, answer):
        app = self.open_app()
        app.checkbox[0].check().run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("private request detail", app.error[0].value)
        self.assertIn("No automatic retry", app.error[0].value)
        answer.assert_called_once()
