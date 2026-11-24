"""Offline checks for Module 13. No workspace, pipeline, job or compute is contacted.

The SDK client and Spark are recording stand-ins, and "running the pipeline" is a small Python model of what the SQL
file declares (bronze keeps every row, silver drops rows that break three rules, gold adds new confirmed tickets to
the history). These tests show what the notebook sends and how its checks behave, not how Databricks runs the SQL.
"""
import contextlib
import csv
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "lib"))
sys.path.insert(0, str(ROOT_DIR / "tests"))
from a8learn import COURSE_ID, OBJECTS, Config, Course, batches
from a8learn.exercises import EXERCISES, REFLECTIONS
from test_agents import ROOT, StandInSpark, rows_of

NOTEBOOK = ROOT / "notebooks/13_pipelines_and_jobs.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
PIPELINE_SQL = (ROOT / "pipelines/a8_bookings.sql").read_text(encoding="utf-8")
WRITES = ("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE", "MERGE")


class PipelineSpark(StandInSpark):
    def sql(self, statement, args=None):
        if "system.lakeflow" in statement:
            self.statements.append(statement)
            return SimpleNamespace(collect=lambda: [{"period_start_time": "2026-11-24 10:00:00",
                                                     "result_state": "SUCCEEDED"}])
        return super().sql(statement, args)


class FakeWorkspace:
    """Records SDK calls. Starting an update runs a Python model of the pipeline over the landed files."""

    def __init__(self, user, incoming, db):
        self.user, self.incoming, self.db, self.calls = user, incoming, db, []
        self.pipeline_specs, self.job_specs, self.processed = {}, {}, set()
        self.pipelines = SimpleNamespace(
            create=self.create_pipeline, list_pipelines=self.list_pipelines, get=self.get_pipeline,
            start_update=self.start_update, get_update=self.get_update, delete=self.delete_pipeline)
        self.jobs = SimpleNamespace(create=self.create_job, list=self.list_jobs, run_now=self.run_now,
                                    get_run=self.get_run, delete=self.delete_job)
        self.tables = SimpleNamespace(delete=self.delete_table)
        self.api_client = SimpleNamespace(do=self.do)
        self.latest_quality = {}

    # ----- pipelines -----
    def create_pipeline(self, **kwargs):
        self.calls.append(("pipelines.create", kwargs))
        self.pipeline_specs["p1"] = kwargs
        return SimpleNamespace(pipeline_id="p1")

    def list_pipelines(self, filter=None):
        return [SimpleNamespace(name=spec["name"], pipeline_id=pid) for pid, spec in self.pipeline_specs.items()]

    def get_pipeline(self, pipeline_id):
        spec = self.pipeline_specs[pipeline_id]
        return SimpleNamespace(pipeline_id=pipeline_id, creator_user_name=spec.get("creator", self.user),
                               spec=SimpleNamespace(configuration=spec["configuration"]))

    def start_update(self, pipeline_id):
        self.calls.append(("pipelines.start_update", pipeline_id))
        self.run_pipeline_model()
        return SimpleNamespace(update_id="u1")

    def get_update(self, pipeline_id, update_id):
        return SimpleNamespace(update=SimpleNamespace(state=SimpleNamespace(value="COMPLETED")))

    def delete_pipeline(self, pipeline_id):
        self.calls.append(("pipelines.delete", pipeline_id))
        self.pipeline_specs.pop(pipeline_id)
        self.processed.clear()

    def run_pipeline_model(self):
        config = next(iter(self.pipeline_specs.values()))["configuration"]
        new_files = [p for p in sorted(Path(config["a8_incoming"]).glob("*.csv")) if p.name not in self.processed]
        self.processed.update(p.name for p in new_files)
        for name in ("bookings_bronze", "bookings_clean"):
            self.db.execute(f"CREATE TABLE IF NOT EXISTS {name} (booking_id TEXT, event_id TEXT, tickets INTEGER, "
                            "status TEXT, source_file TEXT)")
        failed = {"booking_id_present": 0, "tickets_positive": 0, "status_known": 0}
        passed = {key: 0 for key in failed}
        for path in new_files:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    booking_id, tickets = row["booking_id"] or None, int(row["tickets"])
                    self.db.execute("INSERT INTO bookings_bronze VALUES (?, ?, ?, ?, ?)",
                                    (booking_id, row["event_id"], tickets, row["status"], str(path)))
                    checks = {"booking_id_present": booking_id is not None, "tickets_positive": tickets > 0,
                              "status_known": row["status"] in {"confirmed", "cancelled"}}
                    for key, ok in checks.items():
                        passed[key] += ok
                        failed[key] += not ok
                    if all(checks.values()):
                        self.db.execute("INSERT INTO bookings_clean VALUES (?, ?, ?, ?, ?)",
                                        (booking_id, row["event_id"], tickets, row["status"], str(path)))
        self.latest_quality = {k: (passed[k], failed[k]) for k in passed} if new_files else self.latest_quality
        self.db.execute("DROP TABLE IF EXISTS seats_live")
        self.db.execute("""CREATE TABLE seats_live AS SELECT e.event_id, e.event_name, e.city, e.event_date, e.status,
e.capacity, coalesce(sum(b.tickets), 0) AS booked, e.capacity - coalesce(sum(b.tickets), 0) AS available
FROM events e LEFT JOIN (SELECT event_id, tickets FROM bookings WHERE status = 'confirmed' UNION ALL
SELECT event_id, tickets FROM bookings_clean WHERE status = 'confirmed') b ON e.event_id = b.event_id
GROUP BY e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity""")

    def do(self, method, path, body=None, query=None):
        assert method == "GET" and path == "/api/2.0/pipelines/p1/events"
        expectations = [{"dataset": f"cat.schema.{self.course_clean}", "name": name, "passed_records": p,
                         "failed_records": f} for name, (p, f) in self.latest_quality.items()]
        return {"events": [{"event_type": "flow_progress", "details": {"flow_progress": {
            "data_quality": {"expectations": expectations}}}}]}

    # ----- jobs -----
    def create_job(self, **kwargs):
        self.calls.append(("jobs.create", kwargs))
        self.job_specs[7] = kwargs
        return SimpleNamespace(job_id=7)

    def list_jobs(self, name=None):
        return [SimpleNamespace(job_id=jid, creator_user_name=spec.get("creator", self.user),
                                settings=SimpleNamespace(name=spec["name"], tags=spec["tags"]))
                for jid, spec in self.job_specs.items()]

    def run_now(self, job_id):
        self.calls.append(("jobs.run_now", job_id))
        self.run_pipeline_model()
        return SimpleNamespace(run_id=99)

    def get_run(self, run_id):
        return SimpleNamespace(state=SimpleNamespace(life_cycle_state=SimpleNamespace(value="TERMINATED"),
                                                     result_state=SimpleNamespace(value="SUCCESS")))

    def delete_job(self, job_id):
        self.calls.append(("jobs.delete", job_id))
        self.job_specs.pop(job_id)

    def delete_table(self, full_name):
        self.calls.append(("tables.delete", full_name))
        self.db.execute(f"DROP TABLE {full_name.split('.')[-1].replace('a8_offline13_', '')}")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline13", "synthetic@example.com",
                                    "https://example.com"), answers="solutions")

    def run_lesson(self, existing_pipeline=False, reuse=False, **approvals):
        if not reuse:
            self.spark = PipelineSpark(self.course, lambda prompt: None)
            self.addCleanup(self.spark.db.close)
            self.course.spark = self.spark
            self.volume = tempfile.TemporaryDirectory()
            self.addCleanup(self.volume.cleanup)
            self.incoming = Path(self.volume.name) / "incoming"
            self.w = FakeWorkspace(self.course.cfg.user, self.incoming, self.spark.db)
            self.w.course_clean = "bookings_clean"

        class Dbutils:
            pass

        gates = {"create_pipeline": False, "run_pipeline": False, "run_job": False,
                 "delete_pipeline_objects": False, **approvals}
        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}

        def exists(key):
            row = self.spark.db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (key,)).fetchone()
            return row is not None

        with patch.object(Course, "volume_path", new_callable=PropertyMock, return_value=self.volume.name), \
             patch("databricks.sdk.WorkspaceClient", return_value=self.w), patch("time.sleep"), \
             patch.object(self.course, "require"), patch.object(self.course, "guard"), \
             patch.object(self.course, "exists", exists), patch.object(self.course, "links"), \
             patch.object(self.course, "gate", lambda name, label: gates[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            if existing_pipeline:
                self.w.pipeline_specs["p1"] = {"name": self.course.pipeline_name, "configuration": dict(
                    self.course.course_tags)}
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    # ----- the batches -----
    def test_batches_are_deterministic_with_exactly_three_bad_rows(self):
        ids = ["E149", "E150", "E151"]
        one, again, two = batches.new_batch(1, ids), batches.new_batch(1, ids), batches.new_batch(2, ids)
        self.assertEqual(one, again)
        self.assertNotEqual([r["customer_email"] for r in one], [r["customer_email"] for r in two])
        self.assertEqual((len(one), sum(batches.is_valid(r) for r in one)), (43, 40))
        self.assertEqual(len({r["booking_id"] for r in one}), 43)
        bad = [r for r in one if not batches.is_valid(r)]
        self.assertEqual(sorted(("id" if not r["booking_id"] else "status" if r["status"] == "pending" else "tickets")
                                for r in bad), ["id", "status", "tickets"])  # one row per rule
        for number in (1, 2, 3):  # the ids never collide across batches
            self.assertTrue(all(r["booking_id"].startswith(f"N{number}-") or not r["booking_id"]
                                for r in batches.new_batch(number, ids)))
        with self.assertRaises(ValueError):
            batches.new_batch(0, ids)
        csv_text = batches.to_csv(one)
        self.assertEqual(csv_text.splitlines()[0], ",".join(batches.COLUMNS))
        self.assertEqual(len(list(csv.DictReader(io.StringIO(csv_text)))), 43)

    def test_batch_columns_match_the_bookings_table_contract(self):
        with (ROOT / "data/raw/bookings.csv").open(encoding="utf-8") as handle:
            self.assertEqual(next(csv.reader(handle)), batches.COLUMNS)
        self.assertEqual([c.split()[0] for c in batches.SCHEMA.split(",")], batches.COLUMNS)
        self.assertIn(" ".join(batches.SCHEMA.split()), " ".join(PIPELINE_SQL.split()))  # one contract, two places

    # ----- the pipeline file -----
    def test_pipeline_sql_declares_three_layers_and_three_rules_with_known_settings(self):
        self.assertEqual(len(re.findall(r"CREATE OR REFRESH STREAMING TABLE", PIPELINE_SQL)), 2)
        self.assertEqual(len(re.findall(r"CREATE OR REFRESH MATERIALIZED VIEW", PIPELINE_SQL)), 1)
        self.assertEqual(len(re.findall(r"CONSTRAINT \w+ EXPECT", PIPELINE_SQL)), 3)
        self.assertIn("FROM STREAM read_files(", PIPELINE_SQL)
        used = set(re.findall(r"\$\{(\w+)\}", PIPELINE_SQL))
        namespace = self.run_lesson(create_pipeline=True)
        settings = namespace["settings"]
        self.assertEqual(used - set(settings), set())  # every ${name} the file uses is supplied
        self.assertTrue({"a8learn_course", "a8learn_tag"} <= set(settings))
        for forbidden in ("catalog", "workspace", "default."):
            self.assertNotIn(f"{forbidden}.", PIPELINE_SQL.replace("${a8_", ""))  # no hard-coded account names

    # ----- the notebook -----
    def test_default_run_lands_batch_one_and_calls_nothing_else(self):
        namespace = self.run_lesson()
        self.assertEqual(self.w.calls, [])
        files = sorted(p.name for p in self.incoming.glob("*.csv"))
        self.assertEqual(files, ["bookings_batch_1.csv"])
        with (self.incoming / files[0]).open(encoding="utf-8") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 43)
        self.assertEqual([q for q in self.spark.statements if q.lstrip().upper().startswith(WRITES)], [])
        self.assertIsNone(namespace["pipeline_id"])
        self.assertIn("Skipped: no update was run.", self.output)

    def test_create_makes_a_serverless_triggered_tagged_pipeline_and_runs_nothing(self):
        self.run_lesson(create_pipeline=True)
        name, kwargs = self.w.calls[0]
        self.assertEqual(name, "pipelines.create")
        self.assertEqual((kwargs["name"], kwargs["catalog"], kwargs["schema"]),
                         ("a8-offline13-bookings", "workspace", "default"))
        self.assertTrue(kwargs["serverless"] and kwargs["development"] and not kwargs["continuous"])
        self.assertEqual(kwargs["configuration"]["a8learn_course"], COURSE_ID)
        self.assertEqual(kwargs["configuration"]["a8_bronze"], "a8_offline13_bookings_bronze")
        self.assertTrue(kwargs["libraries"][0].notebook.path.replace("\\", "/").endswith("pipelines/a8_bookings"))
        self.assertEqual([c[0] for c in self.w.calls], ["pipelines.create"])

    def test_run_checks_bronze_silver_gold_and_the_independent_calculation(self):
        namespace = self.run_lesson(create_pipeline=True, run_pipeline=True)
        self.assertEqual(namespace["state_1"], "COMPLETED")
        self.assertEqual(namespace["counts"], {"bronze": 43, "silver": 40, "gold": 60})
        self.assertEqual(self.spark.table("bookings_bronze").count(), 86)  # two batches by the end of the lesson
        self.assertEqual(self.spark.table("bookings_clean").count(), 80)
        self.assertIn("tickets_positive", self.output)
        self.assertIn("dropped 1", self.output)
        self.assertEqual([c[0] for c in self.w.calls].count("pipelines.start_update"), 2)
        self.assertIn("static view", self.output)

    def test_second_batch_adds_only_the_new_file(self):
        self.run_lesson(create_pipeline=True, run_pipeline=True)
        self.assertEqual(sorted(p.name for p in self.incoming.glob("*.csv")),
                         ["bookings_batch_1.csv", "bookings_batch_2.csv"])
        self.assertEqual(self.spark.db.execute("SELECT count(DISTINCT source_file) FROM bookings_bronze").fetchone()[0],
                         2)

    def test_rerun_and_rebuild_accept_retained_batches_without_duplicates(self):
        gates = {"create_pipeline": True, "run_pipeline": True, "run_job": True}
        self.run_lesson(**gates)
        namespace = self.run_lesson(reuse=True, **gates, delete_pipeline_objects=True)
        self.assertEqual(namespace["counts"]["bronze"], 129)
        files = {p.name: p.read_bytes() for p in self.incoming.glob("*.csv")}
        namespace = self.run_lesson(reuse=True, **gates)
        self.assertEqual(namespace["counts"], {"bronze": 129, "silver": 120, "gold": 60})
        self.assertTrue(namespace["gold_matches"]([1, 2, 3])[0])
        self.assertEqual({p.name: p.read_bytes() for p in self.incoming.glob("*.csv")}, files)

    def test_job_can_run_without_the_manual_updates(self):
        namespace = self.run_lesson(create_pipeline=True, run_job=True)
        self.assertEqual(namespace["job_state"], "SUCCESS")
        self.assertEqual(self.spark.table("bookings_bronze").count(), 86)  # files 1 and 3 only
        self.assertTrue(namespace["gold_matches"]([1, 3])[0])

    def test_gold_agrees_with_an_independent_python_calculation(self):
        namespace = self.run_lesson(create_pipeline=True, run_pipeline=True)
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        scheduled = [e["event_id"] for e in rows_of("events.csv") if e["status"] == "scheduled"]
        for number in (1, 2):
            for row in batches.new_batch(number, scheduled):
                if batches.is_valid(row) and row["status"] == "confirmed":
                    booked[row["event_id"]] = booked.get(row["event_id"], 0) + int(row["tickets"])
        expected = {e["event_id"]: e["capacity"] - booked.get(e["event_id"], 0) for e in rows_of("events.csv")}
        actual = {r[0]: r[1] for r in self.spark.db.execute("SELECT event_id, available FROM seats_live")}
        self.assertEqual(actual, expected)
        self.assertTrue(namespace["gold_matches"]([1, 2])[0])
        self.assertFalse(namespace["gold_matches"]([1])[0])  # the check can fail

    def test_a_broken_rule_is_caught_by_the_independent_check(self):
        """If silver let a bad row through, gold would disagree and the lesson's check would fail."""
        namespace = self.run_lesson(create_pipeline=True, run_pipeline=True)
        self.spark.db.execute("INSERT INTO bookings_clean VALUES ('X', ?, 3, 'confirmed', 'f')",
                              (namespace["scheduled"][0],))
        self.spark.db.execute("UPDATE seats_live SET available = available - 3 WHERE event_id = ?",
                              (namespace["scheduled"][0],))
        self.assertFalse(namespace["gold_matches"]([1, 2])[0])

    def test_job_is_created_paused_and_tagged_then_run_once_with_batch_three(self):
        namespace = self.run_lesson(create_pipeline=True, run_pipeline=True, run_job=True)
        name, kwargs = next(c for c in self.w.calls if c[0] == "jobs.create")
        self.assertEqual(kwargs["name"], "a8-offline13-refresh")
        self.assertEqual(kwargs["tags"], self.course.course_tags)
        self.assertEqual(kwargs["tasks"][0].pipeline_task.pipeline_id, "p1")
        self.assertEqual(kwargs["schedule"].pause_status.value, "PAUSED")
        self.assertEqual([c[0] for c in self.w.calls].count("jobs.run_now"), 1)
        self.assertEqual(namespace["job_state"], "SUCCESS")
        self.assertEqual(self.spark.table("bookings_bronze").count(), 129)
        self.assertIn("SUCCEEDED", self.output)

    def test_job_without_a_pipeline_does_nothing(self):
        self.run_lesson(run_job=True)
        self.assertEqual(self.w.calls, [])
        self.assertIn("Create the pipeline first", self.output)

    def test_existing_owned_pipeline_is_reused_and_a_foreign_one_stops_the_lesson(self):
        self.run_lesson(existing_pipeline=True, create_pipeline=True)
        self.assertEqual([c for c in self.w.calls if c[0] == "pipelines.create"], [])
        self.assertIn("already exists and is yours", self.output)
        with patch.object(PipelineTests, "run_lesson", PipelineTests.run_lesson):
            pass
        spec = {"name": self.course.pipeline_name, "creator": "other@example.com",
                "configuration": dict(self.course.course_tags)}
        workspace = FakeWorkspace(self.course.cfg.user, self.incoming, self.spark.db)
        workspace.pipeline_specs["p1"] = spec
        from a8learn.lifecycle import pipeline_for_cleanup
        with self.assertRaises(PermissionError):
            pipeline_for_cleanup(self.course, workspace)
        spec["creator"] = self.course.cfg.user
        spec["configuration"] = {"a8learn_course": COURSE_ID, "a8learn_tag": "someone_else"}
        with self.assertRaises(PermissionError):
            pipeline_for_cleanup(self.course, workspace)

    def test_delete_removes_the_job_then_the_pipeline_then_the_tables(self):
        self.run_lesson(create_pipeline=True, run_pipeline=True, run_job=True, delete_pipeline_objects=True)
        names = [c[0] for c in self.w.calls if c[0].endswith("delete")]
        self.assertEqual(names, ["jobs.delete", "pipelines.delete", "tables.delete", "tables.delete",
                                 "tables.delete"])
        tables = [c[1] for c in self.w.calls if c[0] == "tables.delete"]
        self.assertEqual(tables, ["workspace.default.a8_offline13_seats_live",
                                  "workspace.default.a8_offline13_bookings_clean",
                                  "workspace.default.a8_offline13_bookings_bronze"])
        self.assertIn("Removed:", self.output)

    def test_delete_with_nothing_to_delete_is_a_message(self):
        self.run_lesson(delete_pipeline_objects=True)
        self.assertEqual([c for c in self.w.calls if c[0].endswith("delete")], [])
        self.assertIn("nothing", self.output)

    def test_exercise_solutions_match_independent_python(self):
        self.run_lesson(create_pipeline=True, run_pipeline=True)
        scheduled = [e["event_id"] for e in rows_of("events.csv") if e["status"] == "scheduled"]
        new = {}
        for number in (1, 2):
            for row in batches.new_batch(number, scheduled):
                if batches.is_valid(row) and row["status"] == "confirmed":
                    new[row["event_id"]] = new.get(row["event_id"], 0) + int(row["tickets"])
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["13.1"]["solution"]).collect()]
        self.assertEqual(rows, sorted(new.items(), key=lambda kv: (-kv[1], kv[0])))
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        left = [(e["event_name"], e["city"], e["capacity"] - booked.get(e["event_id"], 0) - new.get(e["event_id"], 0))
                for e in rows_of("events.csv") if e["status"] == "scheduled"]
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["13.2"]["solution"]).collect()]
        self.assertEqual(rows, sorted((r for r in left if r[2] < 30), key=lambda r: (r[2], r[0], r[1])))
        self.assertTrue(rows)

    def test_blank_and_naive_exercise_answers_fail(self):
        self.run_lesson(create_pipeline=True, run_pipeline=True)
        self.course.test_with_solutions = False
        naive = ("SELECT event_id, sum(tickets) AS new_tickets FROM IDENTIFIER(a8_bookings_clean) "
                 "GROUP BY event_id ORDER BY new_tickets DESC, event_id")  # counts cancelled tickets too
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("13.1", ""))
            self.assertFalse(self.course.check("13.1", naive))

    def test_exercises_are_skipped_not_failed_before_the_pipeline_has_run(self):
        self.run_lesson()
        self.assertIn("Skipped: the cleaned bookings table does not exist yet", self.output)

    def test_notebook_standard_scope_and_navigation(self):
        for key in ("bookings_bronze", "bookings_clean", "seats_live"):
            self.assertEqual(OBJECTS[key], ("pipeline_table", "13_pipelines_and_jobs"))
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "If it differs", "Cost boundary"):
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 4)
        self.assertEqual({"13.a", "13.b"} - set(REFLECTIONS), set())
        for forbidden in ("A8.run", "A8.sql", "DROP ", "mlflow", "serving_endpoints"):
            self.assertNotIn(forbidden, SOURCE)
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/12_deploy_and_govern.py"):
            self.assertIn("13_pipelines_and_jobs", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 13", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))


class PipelineCleanupTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "smoke", "student@example.com", "https://example.com"))
        self.w, self.client = Mock(), Mock()
        from databricks.sdk.errors import NotFound
        self.NotFound = NotFound
        self.w.vector_search_indexes.get_index.side_effect = NotFound("none")
        self.w.vector_search_endpoints.get_endpoint.side_effect = NotFound("none")
        self.w.apps.get.side_effect = NotFound("none")
        self.w.serving_endpoints.get.side_effect = NotFound("none")
        self.mine = self.course.cfg.user
        self.pipeline = SimpleNamespace(name="a8-smoke-bookings", pipeline_id="p1")
        self.info = SimpleNamespace(pipeline_id="p1", creator_user_name=self.mine, spec=SimpleNamespace(
            configuration={"a8learn_course": COURSE_ID, "a8learn_tag": "smoke"}))
        self.job = SimpleNamespace(job_id=5, creator_user_name=self.mine, settings=SimpleNamespace(
            name="a8-smoke-refresh", tags={"a8learn_course": COURSE_ID, "a8learn_tag": "smoke"}))
        self.w.pipelines.list_pipelines.return_value = [self.pipeline]
        self.w.pipelines.get.return_value = self.info
        self.w.jobs.list.return_value = [self.job]

    def full_cleanup(self):
        from a8learn.lifecycle import cleanup
        self.client.get_experiment_by_name.return_value = None
        with patch("a8learn.lifecycle.model_for_cleanup", return_value=None), \
             patch.object(self.course, "exists", return_value=False):
            return cleanup(self.course, self.w, self.client, "smoke", tables=True)

    def test_endpoint_only_does_not_inspect_or_delete_apps_jobs_or_pipelines(self):
        from a8learn.lifecycle import cleanup
        result = cleanup(self.course, self.w, self.client, "smoke")
        self.assertFalse(result["app_deleted"] or result["job_deleted"] or result["pipeline_deleted"])
        self.w.apps.get.assert_not_called()
        self.w.jobs.list.assert_not_called()
        self.w.pipelines.list_pipelines.assert_not_called()
        self.w.workspace.delete.assert_not_called()

    def test_job_then_pipeline_are_deleted_for_their_owner(self):
        result = self.full_cleanup()
        self.assertTrue(result["pipeline_deleted"] and result["job_deleted"])
        self.w.jobs.delete.assert_called_once_with(5)
        self.w.pipelines.delete.assert_called_once_with("p1")
        order = [c[0] for c in self.w.mock_calls if c[0] in {"jobs.delete", "pipelines.delete"}]
        self.assertEqual(order, ["jobs.delete", "pipelines.delete"])

    def test_foreign_pipeline_or_job_stops_cleanup_before_any_delete(self):
        self.info.creator_user_name = "other@example.com"
        with self.assertRaises(PermissionError):
            self.full_cleanup()
        self.info.creator_user_name = self.mine
        self.job.settings.tags = {}
        with self.assertRaises(PermissionError):
            self.full_cleanup()
        self.w.jobs.delete.assert_not_called()
        self.w.pipelines.delete.assert_not_called()

    def test_similar_names_are_never_matched(self):
        from a8learn.lifecycle import job_for_cleanup, pipeline_for_cleanup
        self.pipeline.name = "a8-smoke-bookings-copy"
        self.job.settings.name = "a8-smoke-refresh2"
        self.assertIsNone(pipeline_for_cleanup(self.course, self.w))
        self.assertIsNone(job_for_cleanup(self.course, self.w))

    def test_full_cleanup_deletes_pipeline_tables_through_the_api_in_dependency_order(self):
        from a8learn.lifecycle import cleanup

        class Missing(Exception):
            error_code = "RESOURCE_DOES_NOT_EXIST"

        present = {"seats_live", "bookings_clean", "bookings_bronze", "bookings", "events", "raw"}
        statements = []
        self.client.get_registered_model.side_effect = Missing()
        self.client.get_experiment_by_name.return_value = None
        fake_mlflow = SimpleNamespace(exceptions=SimpleNamespace(MlflowException=Missing))
        with patch.dict(sys.modules, {"mlflow": fake_mlflow}), \
             patch.object(self.course, "exists", side_effect=lambda key: key in present), \
             patch.object(self.course, "guard"), \
             patch.object(self.course, "run", side_effect=lambda s: statements.append(s)):
            result = cleanup(self.course, self.w, self.client, "smoke", tables=True)
        self.assertEqual(result["data_objects_deleted"], 6)
        deleted = [c.args[0] for c in self.w.tables.delete.call_args_list]
        self.assertEqual(deleted, ["workspace.default.a8_smoke_seats_live", "workspace.default.a8_smoke_bookings_clean",
                                   "workspace.default.a8_smoke_bookings_bronze"])
        self.assertTrue(all("seats_live" not in s and "bookings_clean" not in s for s in statements))  # not DROPped
        self.assertEqual(len(statements), 3)  # bookings, events and the volume


if __name__ == "__main__":
    unittest.main()
