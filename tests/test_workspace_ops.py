import unittest
from unittest.mock import Mock, patch

from helpers import FakeSpark
from logic import load_events, ownership_marker
from workspace_ops import check_table, cleanup, deploy_app, ensure_app, ensure_table, get_app

ARGS = ("training", "authorised", "learner07")


class WorkspaceOperationTests(unittest.TestCase):
    def test_table_create_is_atomic_and_rerun_has_no_write(self):
        spark = FakeSpark()
        table = ensure_table(spark, *ARGS, load_events())
        self.assertEqual(table, "training.authorised.a8learn_learner07_events")
        creates = [s for s in spark.statements if s.startswith("CREATE")]
        self.assertEqual(len(creates), 1)
        self.assertIn("USING DELTA COMMENT 'a8-databricks-learning-pilot-v1:learner07' AS SELECT", creates[0])
        self.assertNotIn("REPLACE", creates[0])
        self.assertEqual(len(spark.dropped_views), 1)
        spark.statements.clear()
        ensure_table(spark, *ARGS, load_events())
        self.assertFalse(any(s.startswith(("CREATE", "INSERT", "DROP")) for s in spark.statements))

    def test_table_collision_and_changed_data_preserved(self):
        for spark in (FakeSpark(True, "unrelated"), FakeSpark(True, rows=[])):
            with self.assertRaises(ValueError):
                ensure_table(spark, *ARGS, load_events())
            self.assertTrue(spark.exists)
            self.assertFalse(any(s.startswith(("CREATE", "DROP", "INSERT")) for s in spark.statements))

    def test_interrupted_create_cleans_only_temp_view(self):
        spark = FakeSpark()
        spark.fail_create = True
        with self.assertRaises(RuntimeError):
            ensure_table(spark, *ARGS, load_events())
        self.assertFalse(spark.exists)
        self.assertEqual(len(spark.dropped_views), 1)

    def test_get_app_absence_vs_permission(self):
        from databricks.sdk.errors import NotFound, PermissionDenied
        workspace = Mock()
        workspace.api_client.do.side_effect = NotFound("absent")
        self.assertIsNone(get_app(workspace, "a8learn-learner07-assistant"))
        workspace.api_client.do.side_effect = PermissionDenied("denied")
        with self.assertRaises(PermissionDenied):
            get_app(workspace, "a8learn-learner07-assistant")

    @patch("workspace_ops.get_app", return_value=None)
    def test_create_app_payload_matches_sdk_schema(self, get):
        from databricks.sdk.service.apps import App
        workspace = Mock()
        ensure_app(workspace, *ARGS, "approved-model")
        body = workspace.api_client.do.call_args.kwargs["body"]
        self.assertEqual(body, App.from_dict(body).as_dict())
        self.assertEqual(body["description"], ownership_marker("learner07"))
        self.assertEqual(body["resources"], [{"name": "model", "serving_endpoint": {
            "name": "approved-model", "permission": "CAN_QUERY",
        }}])

    def test_reuse_never_reconfigures_and_collision_never_writes(self):
        for marker, should_pass in [(ownership_marker("learner07"), True), ("other", False)]:
            workspace = Mock()
            with patch("workspace_ops.get_app", return_value={"description": marker}):
                if should_pass:
                    ensure_app(workspace, *ARGS, "approved")
                else:
                    with self.assertRaises(ValueError):
                        ensure_app(workspace, *ARGS, "approved")
            workspace.api_client.do.assert_not_called()

    def test_deploy_checks_path_and_ownership_before_write(self):
        workspace = Mock()
        for path in ("C:/local/app/event_assistant", "/Workspace/repo", "/Workspace/../app/event_assistant"):
            with self.assertRaises(ValueError):
                deploy_app(workspace, *ARGS, path)
        with patch("workspace_ops.get_app", return_value={"description": "other"}):
            with self.assertRaises(ValueError):
                deploy_app(workspace, *ARGS, "/Workspace/personal/repo/app/event_assistant")
        workspace.api_client.do.assert_not_called()
        with patch("workspace_ops.get_app", return_value={"description": ownership_marker("learner07")}):
            deploy_app(workspace, *ARGS, "/Workspace/personal/repo/app/event_assistant")
        method, url = workspace.api_client.do.call_args.args
        self.assertEqual((method, url), ("POST", "/api/2.0/apps/a8learn-learner07-assistant/deployments"))
        self.assertEqual(workspace.api_client.do.call_args.kwargs["body"]["mode"], "SNAPSHOT")

    def test_cleanup_all_candidates_preflight_before_any_delete(self):
        for table_marker, app_marker in [
            ("other", ownership_marker("learner07")), (ownership_marker("learner07"), "other"),
        ]:
            workspace, spark = Mock(), FakeSpark(True, table_marker)
            with patch("workspace_ops.get_app", return_value={"description": app_marker}):
                with self.assertRaises(ValueError):
                    cleanup(workspace, spark, *ARGS, "learner07")
            workspace.api_client.do.assert_not_called()
            self.assertTrue(spark.exists)
            self.assertFalse(any(s.startswith("DROP") for s in spark.statements))

    def test_cleanup_confirmation_then_partial_and_repeated_teardown(self):
        workspace, spark = Mock(), FakeSpark(True)
        with self.assertRaises(ValueError):
            cleanup(workspace, spark, *ARGS, "")
        workspace.api_client.do.assert_not_called()
        with patch("workspace_ops.get_app", return_value={"description": ownership_marker("learner07")}):
            cleanup(workspace, spark, *ARGS, "learner07")
        workspace.api_client.do.assert_called_once_with("DELETE", "/api/2.0/apps/a8learn-learner07-assistant")
        self.assertFalse(spark.exists)
        with patch("workspace_ops.get_app", return_value=None):
            cleanup(workspace, spark, *ARGS, "learner07")
        self.assertEqual(workspace.api_client.do.call_count, 1)
        spark = FakeSpark(True)
        with patch("workspace_ops.get_app", return_value=None):
            cleanup(workspace, spark, *ARGS, "learner07")
        self.assertFalse(spark.exists)

    def test_cleanup_delete_failure_preserves_table_and_can_resume(self):
        workspace, spark = Mock(), FakeSpark(True)
        workspace.api_client.do.side_effect = RuntimeError("delete failed")
        with patch("workspace_ops.get_app", return_value={"description": ownership_marker("learner07")}):
            with self.assertRaises(RuntimeError):
                cleanup(workspace, spark, *ARGS, "learner07")
        self.assertTrue(spark.exists)
        workspace.api_client.do.side_effect = None
        with patch("workspace_ops.get_app", return_value=None):
            cleanup(workspace, spark, *ARGS, "learner07")
        self.assertFalse(spark.exists)
