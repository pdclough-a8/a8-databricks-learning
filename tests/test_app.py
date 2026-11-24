"""Offline checks for Module 11. No workspace, app, warehouse or grant is contacted.

The SDK client is a recording stand-in. These tests show what the notebook sends and what cleanup refuses; they do
not show how Databricks Apps runs the Streamlit source (see docs/validation.md for live status).
"""
import ast
import contextlib
import io
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "lib"))
sys.path.insert(0, str(ROOT_DIR / "tests"))
from a8learn import COURSE_ID, Config, Course
from a8learn.app_deploy import app_description, app_for_cleanup, app_yaml, delete_app
from a8learn.exercises import EXERCISES, REFLECTIONS
from databricks.sdk.errors import NotFound
from test_agents import ROOT, StandInSpark, rows_of

NOTEBOOK = ROOT / "notebooks/11_interactive_app.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
APP_SOURCE = (ROOT / "app/a8_events/app.py").read_text(encoding="utf-8")


class FakeApps:
    def __init__(self, user, description):
        self.calls, self.exists, self.user, self.description = [], False, user, description

    def make(self):
        return SimpleNamespace(
            name="a8-offline11-events", creator=self.user, description=self.description, url="https://app.example",
            service_principal_name="app-1 a8-offline11-events", service_principal_client_id="sp-client-id",
            resources=[SimpleNamespace(sql_warehouse=SimpleNamespace(id="wh1"))],
            app_status=SimpleNamespace(state=SimpleNamespace(value="RUNNING")))

    def get(self, name):
        if not self.exists:
            raise NotFound("none")
        return self.make()

    def create_and_wait(self, app):
        self.calls.append(("apps.create", app))
        self.exists = True
        return self.make()

    def deploy_and_wait(self, app_name, app_deployment):
        self.calls.append(("apps.deploy", app_deployment.source_code_path))
        return SimpleNamespace(status=SimpleNamespace(state=SimpleNamespace(value="SUCCEEDED"), message="ok"))

    def delete(self, name):
        self.calls.append(("apps.delete", name))
        self.exists = False


class FakeWorkspace:
    def __init__(self, user, description):
        self.apps = FakeApps(user, description)
        self.uploads, self.deleted_folders = {}, []
        self.warehouses = SimpleNamespace(list=lambda: [SimpleNamespace(id="wh1")])
        self.config = SimpleNamespace(authenticate=lambda: {"Authorization": "Bearer x"})
        self.workspace = SimpleNamespace(
            mkdirs=lambda path: self.apps.calls.append(("mkdirs", path)),
            upload=lambda path, data, **kw: self.uploads.__setitem__(path, data),
            delete=lambda path, recursive: self.deleted_folders.append(path))


class AppSpark(StandInSpark):
    """SQLite cannot run Unity Catalog privilege statements, so they are recorded and answered with no rows."""

    def sql(self, statement, args=None):
        if statement.lstrip().upper().startswith(("GRANT", "REVOKE", "SHOW GRANTS")):
            self.statements.append(statement)
            return SimpleNamespace(collect=lambda: [])
        return super().sql(statement, args)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline11", "synthetic@example.com",
                                    "https://example.com"), answers="solutions")

    def run_lesson(self, existing=False, **approvals):
        self.spark = AppSpark(self.course, lambda prompt: None)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.w = FakeWorkspace(self.course.cfg.user, app_description(self.course))
        self.w.apps.exists = existing
        gates = {"create_app": False, "grant_app_access": False, "deploy_app": False, "delete_app": False,
                 **approvals}
        namespace = {"A8": self.course, "spark": self.spark, "dbutils": object, "ROOT": ROOT,
                     "display": lambda *_: None}
        reply = Mock(status=200)
        reply.__enter__ = lambda s: s
        reply.__exit__ = lambda *a: None
        with patch("databricks.sdk.WorkspaceClient", return_value=self.w), patch("time.sleep"), \
             patch("urllib.request.urlopen", return_value=reply), \
             patch.object(self.course, "require"), patch.object(self.course, "links"), \
             patch.object(self.course, "exists", lambda key: True), \
             patch.object(self.course, "gate", lambda name, label: gates[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    def test_default_run_reads_only_and_calls_nothing(self):
        self.run_lesson()
        self.assertEqual(self.w.apps.calls, [])
        self.assertEqual(self.w.uploads, {})
        self.assertEqual([q for q in self.spark.statements if q.lstrip().upper().startswith(("GRANT", "CREATE"))], [])
        self.assertIn("Skipped. Reading the app above", self.output)

    def test_create_writes_two_files_and_attaches_the_warehouse_with_the_course_marker(self):
        namespace = self.run_lesson(create_app=True)
        self.assertEqual(sorted(self.w.uploads), [f"{self.course.app_folder}/app.py",
                                                  f"{self.course.app_folder}/app.yaml"])
        app = dict(self.w.apps.calls)["apps.create"]
        self.assertEqual((app.name, app.description), ("a8-offline11-events", app_description(self.course)))
        resource = app.resources[0]
        self.assertEqual((resource.name, resource.sql_warehouse.id, resource.sql_warehouse.permission.value),
                         ("warehouse", "wh1", "CAN_USE"))
        self.assertIsNotNone(namespace["app"])
        self.assertEqual([c[0] for c in self.w.apps.calls if c[0] == "apps.deploy"], [])

    def test_grants_are_least_privilege_and_only_after_approval(self):
        self.run_lesson(create_app=True, grant_app_access=True)
        grants = [q for q in self.spark.statements if q.lstrip().upper().startswith("GRANT")]
        self.assertEqual(len(grants), 3)
        self.assertTrue(all("`sp-client-id`" in g for g in grants))
        self.assertEqual(sorted(g.split(" ON ")[0] for g in grants),
                         ["GRANT SELECT", "GRANT USE CATALOG", "GRANT USE SCHEMA"])
        self.assertFalse(any("ALL PRIVILEGES" in g.upper() or "MODIFY" in g.upper() for g in grants))
        self.assertNotIn("DROP", " ".join(grants).upper())

    def test_deploy_uses_a_workspace_prefixed_path(self):
        self.run_lesson(create_app=True, deploy_app=True)
        self.assertIn(("apps.deploy", f"/Workspace{self.course.app_folder}"), self.w.apps.calls)

    def test_existing_owned_app_is_reused_and_a_foreign_one_stops_the_lesson(self):
        self.run_lesson(existing=True, create_app=True)
        self.assertEqual([c[0] for c in self.w.apps.calls], [])
        self.assertIn("already exists and is yours", self.output)
        with self.assertRaises(PermissionError):
            self.run_lesson_foreign()

    def run_lesson_foreign(self):
        self.spark = AppSpark(self.course, lambda prompt: None)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        w = FakeWorkspace("someone.else@example.com", app_description(self.course))
        w.apps.exists = True
        with patch("databricks.sdk.WorkspaceClient", return_value=w):
            return app_for_cleanup(self.course, w)

    def test_delete_revokes_then_deletes_the_app_then_the_folder(self):
        self.run_lesson(existing=True, delete_app=True)
        order = [c[0] for c in self.w.apps.calls]
        self.assertEqual(order, ["apps.delete"])
        self.assertEqual(self.w.deleted_folders, [self.course.app_folder])
        revokes = [q for q in self.spark.statements if q.lstrip().upper().startswith("REVOKE")]
        self.assertEqual(len(revokes), 3)

    def test_delete_with_nothing_to_delete_is_a_message(self):
        self.run_lesson(delete_app=True)
        self.assertEqual([c for c in self.w.apps.calls if c[0] == "apps.delete"], [])
        self.assertIn("no app of yours", self.output)

    def test_cleanup_refuses_an_app_without_the_course_marker(self):
        w = FakeWorkspace(self.course.cfg.user, "someone's unrelated app")
        w.apps.exists = True
        with self.assertRaises(PermissionError):
            delete_app(self.course, w)
        self.assertEqual(w.apps.calls, [])
        self.assertEqual(w.deleted_folders, [])

    def test_settings_file_reads_the_warehouse_resource_and_names_the_view(self):
        text = app_yaml(self.course)
        self.assertIn("valueFrom: warehouse", text)
        self.assertIn(self.course.t("event_availability"), text)
        self.assertIn('command: ["streamlit", "run", "app.py"]', text)

    def test_app_source_is_read_only_and_carries_no_credentials(self):
        ast.parse(APP_SOURCE)
        for word in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "token", "secret", "password"):
            self.assertNotIn(word.lower(), APP_SOURCE.lower().replace("create_", ""), word)
        self.assertIn("A8_WAREHOUSE_ID", APP_SOURCE)
        self.assertIn("X-Forwarded-Email", APP_SOURCE)

    def test_exercise_solution_matches_independent_python_and_naive_answer_fails(self):
        self.spark = AppSpark(self.course, lambda prompt: None)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        expected = sum(1 for e in rows_of("events.csv")
                       if e["status"] == "scheduled" and e["capacity"] - booked.get(e["event_id"], 0) < 30)
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["11.1"]["solution"]).collect()]
        self.assertEqual(rows, [(expected,)])
        self.assertGreater(expected, 0)
        self.course.test_with_solutions = False
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("11.1", ""))
            self.assertFalse(self.course.check(
                "11.1", "SELECT count(*) FROM IDENTIFIER(a8_event_availability) WHERE available < 30"))

    def test_notebook_standard_scope_and_navigation(self):
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "If it differs", "Cost boundary"):
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 4)
        self.assertEqual({"11.a", "11.b"} - set(REFLECTIONS), set())
        for forbidden in ("A8.run", "A8.sql", "DROP ", "mlflow", "serving_endpoints"):
            self.assertNotIn(forbidden, SOURCE)
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py"):
            self.assertIn("11_interactive_app", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 11", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))
        self.assertEqual(COURSE_ID in app_description(self.course), True)


if __name__ == "__main__":
    unittest.main()
