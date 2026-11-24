"""Offline execution of the real lesson SQL, checked against independent CSV aggregations.

SQLite exercises the relational logic, not Spark/Unity Catalog permissions or the UI.
Only CREATE OR REPLACE VIEW syntax is adapted; SELECT text runs unchanged.
"""
import ast
import contextlib
import csv
import io
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from a8learn import Config, Course, OBJECTS
from a8learn.exercises import EXERCISES

NOTEBOOK = ROOT / "notebooks/03_descriptive_analytics.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
INTEGER_FIELDS = {"start_hour", "capacity", "price_gbp", "tickets", "rating"}
FIELDS = [
    "event_id", "event_name", "topic", "format", "city", "event_date", "event_status",
    "capacity", "confirmed_bookings", "confirmed_tickets", "available_seats", "fill_rate",
    "known_outcome_tickets", "attended_tickets", "attendance_rate",
    "feedback_count", "rating_sum", "average_rating",
]


def read_fixture(name):
    with (ROOT / "data/raw" / f"{name}.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        for field in INTEGER_FIELDS & row.keys():
            row[field] = int(row[field])
        if "attended" in row:
            row["attended"] = {"true": True, "false": False, "": None}[row["attended"]]
    return rows


class Result:
    def __init__(self, cursor):
        self.columns = [c[0] for c in cursor.description] if cursor.description else []
        self.rows = cursor.fetchall()

    def first(self):
        return self.rows[0]

    def collect(self):
        return self.rows

    def count(self):
        return len(self.rows)


class OfflineSpark:
    """A tiny SQL adapter: no SDK, network, Spark installation or credentials."""

    def __init__(self, course):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.course = course
        self.statements = []

    def sql(self, statement):
        self.statements.append(statement)
        for key in OBJECTS:
            statement = statement.replace(f"IDENTIFIER(a8_{key})", key).replace(self.course.t(key), key)
        match = re.fullmatch(r"CREATE OR REPLACE VIEW (\w+)\s+COMMENT '[^']*'\s+AS (.+)", statement, re.S)
        if match:
            name, select = match.groups()
            self.db.execute(f"DROP VIEW IF EXISTS {name}")
            statement = f"CREATE VIEW {name} AS {select}"
        return Result(self.db.execute(statement))

    def table(self, name):
        return self.sql(f"SELECT * FROM {name}")

    def load(self, key, rows):
        columns = list(rows[0])
        definitions = ", ".join(
            f"{col} {'INTEGER' if col in INTEGER_FIELDS or col == 'attended' else 'TEXT'}" for col in columns
        )
        self.db.execute(f"CREATE TABLE {key} ({definitions})")
        self.db.executemany(f"INSERT INTO {key} VALUES ({','.join('?' for _ in columns)})",
                            [tuple(row[col] for col in columns) for row in rows])


def independent_metrics(events, bookings, feedback):
    """Python loops over shipped rows, deliberately not a translation of the CTE join."""
    result = {}
    for event in events:
        eid = event["event_id"]
        confirmed = [b for b in bookings if b["event_id"] == eid and b["status"] == "confirmed"]
        responses = [f for f in feedback if f["event_id"] == eid]
        tickets = sum(b["tickets"] for b in confirmed)
        known = [b for b in confirmed if b["attended"] is not None] if event["status"] == "completed" else []
        known_tickets = sum(b["tickets"] for b in known)
        attended = sum(b["tickets"] for b in known if b["attended"]) if known_tickets else None
        rating_sum = sum(f["rating"] for f in responses)
        result[eid] = [
            eid, event["event_name"], event["topic"], event["format"], event["city"], event["event_date"],
            event["status"], event["capacity"], len(confirmed), tickets, event["capacity"] - tickets,
            tickets / event["capacity"] if event["capacity"] else None,
            known_tickets, attended, attended / known_tickets if known_tickets else None,
            len(responses), rating_sum, rating_sum / len(responses) if responses else None,
        ]
    return result


class DescriptiveTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline8", "synthetic@example.com", "https://example.com"),
                             answers="solutions")
        self.spark = OfflineSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.events, self.bookings, self.feedback = [read_fixture(k) for k in ("events", "bookings", "feedback")]
        for key, rows in [("events", self.events), ("bookings", self.bookings), ("feedback", self.feedback)]:
            self.spark.load(key, rows)
        self.namespace = {"A8": self.course, "spark": self.spark, "display": lambda frame: frame.collect(),
                          "ROOT": ROOT}
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dashboard_file = Path(folder.name) / "A8 offline8 event snapshot.lvdash.json"
        self.workspace = Mock()

    def run_lesson(self, approved=True, exists=lambda key: True, gates=None):
        # These mocks replace ownership/availability reads only, never the taught SELECT queries.
        with patch.object(self.course, "exists", side_effect=exists), \
             patch.object(self.course, "guard") as guard, \
             patch.object(self.course, "gate",
                          side_effect=lambda name, _label: (gates or {}).get(name, approved)), \
             patch.object(Course, "dashboard_path", new_callable=PropertyMock, return_value=self.dashboard_file), \
             patch("databricks.sdk.WorkspaceClient", self.workspace), \
             contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), self.namespace)
        return guard

    def values(self, query):
        return [tuple(row) for row in self.spark.sql(query).collect()]

    def python_rows(self):
        expected = independent_metrics(self.events, self.bookings, self.feedback)
        return [dict(zip(FIELDS, values, strict=True)) for values in expected.values()]

    def test_full_notebook_sql_and_exercises_on_shipped_csvs(self):
        guard = self.run_lesson()
        guard.assert_called_once_with("event_metrics")
        actual = self.spark.table(self.course.t("event_metrics"))
        self.assertEqual(actual.columns, FIELDS)
        expected = independent_metrics(self.events, self.bookings, self.feedback)
        self.assertEqual(len(actual.rows), 60)
        self.assertEqual(set(expected), {row["event_id"] for row in actual.rows})
        for row in actual.rows:
            with self.subTest(event=row["event_id"]):
                self.assertEqual(list(row), expected[row["event_id"]])
        self.assertEqual(sum(row["event_status"] == "scheduled" for row in actual.rows), 12)
        # The entire Python source, including real A8.check in instructor mode, executed.
        self.assertTrue(self.course.test_with_solutions)
        self.assertIn("answer_3_2", self.namespace)

    def test_default_no_skips_write_and_stops_at_require(self):
        with self.assertRaisesRegex(RuntimeError, "Missing prerequisites: a8_offline8_event_metrics"):
            self.run_lesson(approved=False, exists=lambda key: key != "event_metrics")
        self.assertFalse(any("CREATE" in query or "DROP" in query for query in self.spark.statements))
        self.assertIs(self.namespace["create_reporting_view"], False)

    def test_gate_cell_finishes_before_the_write_cell(self):
        cells = SOURCE.split("# COMMAND ----------")
        gate = next(i for i, c in enumerate(cells) if 'A8.gate("create_reporting_view"' in c)
        write = next(i for i, c in enumerate(cells) if "CREATE OR REPLACE VIEW" in c)
        self.assertLess(gate, write)
        self.assertNotIn("raise", cells[gate])

    def test_no_mocked_approval_is_required_by_default_gate(self):
        self.course.dbutils = Mock()
        self.course.dbutils.widgets.get.return_value = "no"
        # Exercise the actual default-no plumbing used by this lesson.
        self.assertFalse(self.course.gate("create_reporting_view", "Approve view?"))
        self.course.dbutils.widgets.dropdown.assert_called_once_with(
            "create_reporting_view", "no", ["no", "yes"], "Approve view?")

    def test_ownership_failure_stops_before_create(self):
        with patch.object(self.course, "exists", return_value=True), \
             patch.object(self.course, "gate", return_value=True), \
             patch.object(self.course, "guard", side_effect=PermissionError("collision")), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(PermissionError, "collision"):
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), self.namespace)
        self.assertFalse(any("CREATE" in query for query in self.spark.statements))

    def test_view_marker_rejects_unmarked_or_foreign_existing_object(self):
        course = Course(self.course.cfg, spark=Mock())
        for owner, marker in [
            ("other@example.com", "a8-databricks-learning owned elsewhere"),
            (course.cfg.user, "unrelated"),
            (course.cfg.user, None),
        ]:
            with self.subTest(owner=owner, marker=marker), \
                 patch.object(course, "_info", return_value=owner), self.assertRaises(PermissionError):
                course.spark.sql.return_value.collect.return_value = [{"marker": marker}]
                course.guard("event_metrics")
        with patch.object(course, "_info", return_value=course.cfg.user):
            course.spark.sql.return_value.collect.return_value = [{"marker": "a8-databricks-learning event metrics"}]
            course.guard("event_metrics")

    def test_repeated_and_resumed_view_creation_does_not_drift_sources(self):
        self.run_lesson()
        before = self.values("SELECT * FROM event_metrics ORDER BY event_id")
        sources = {key: self.values(f"SELECT * FROM {key}") for key in ["events", "bookings", "feedback"]}
        self.run_lesson()
        self.assertEqual(self.values("SELECT * FROM event_metrics ORDER BY event_id"), before)
        # Re-enter the lesson from a fresh Python namespace with an existing view.
        self.namespace = {"A8": self.course, "spark": self.spark, "display": lambda frame: frame.collect(),
                          "ROOT": ROOT}
        self.run_lesson()
        self.assertEqual(self.values("SELECT * FROM event_metrics ORDER BY event_id"), before)
        for key, rows in sources.items():
            self.assertEqual(self.values(f"SELECT * FROM {key}"), rows)

    def test_dashboard_filter_states_against_independent_source_aggregation(self):
        self.run_lesson()
        rows = self.python_rows()
        predicates = {
            "all_events": lambda row: True,
            "scheduled_events": lambda row: row["event_status"] == "scheduled",
            "scheduled_leeds": lambda row: row["event_status"] == "scheduled" and row["city"] == "Leeds",
            "scheduled_leeds_december": lambda row: row["event_status"] == "scheduled" and row["city"] == "Leeds"
            and "2026-12-01" <= row["event_date"] <= "2026-12-31",
        }
        self.assertEqual(set(self.namespace["dashboard_checks"]), set(predicates))
        for name, predicate in predicates.items():
            filtered = [row for row in rows if predicate(row)]
            with self.subTest(filter_state=name):
                self.assertTrue(filtered, "Use a meaningful, nonempty fixture filter checkpoint")
                self.assertEqual(self.values(self.namespace["dashboard_checks"][name]),
                                 [(len(filtered), sum(r["confirmed_tickets"] for r in filtered))])
        dataset = self.spark.sql(self.namespace["dashboard_sql"])
        self.assertEqual(dataset.count(), 60)
        self.assertEqual(dataset.columns, FIELDS)

    def test_genie_examples_and_held_out_answers_have_independent_gold_results(self):
        self.run_lesson()
        rows = self.python_rows()
        status_counts = defaultdict(int)
        city_tickets = defaultdict(int)
        topic_feedback = defaultdict(lambda: [0, 0])
        format_attendance = defaultdict(lambda: [0, 0])
        topic_fill = defaultdict(lambda: [0, 0])
        leeds = []
        for row in rows:
            status_counts[row["event_status"]] += 1
            if row["event_status"] == "scheduled":
                city_tickets[row["city"]] += row["confirmed_tickets"]
                topic_fill[row["topic"]][0] += row["confirmed_tickets"]
                topic_fill[row["topic"]][1] += row["capacity"]
                if row["city"] == "Leeds":
                    leeds.append((row["event_id"], row["available_seats"]))
            else:
                topic_feedback[row["topic"]][0] += row["feedback_count"]
                topic_feedback[row["topic"]][1] += row["rating_sum"]
                format_attendance[row["format"]][0] += row["attended_tickets"] or 0
                format_attendance[row["format"]][1] += row["known_outcome_tickets"]
        expected = [
            sorted(status_counts.items()), sorted(city_tickets.items()),
            sorted((topic, count, round(total / count, 2)) for topic, (count, total) in topic_feedback.items()),
            sorted(leeds),
            sorted((fmt, round(100 * a / n, 2)) for fmt, (a, n) in format_attendance.items()),
            sorted((topic, round(100 * tickets / cap, 2)) for topic, (tickets, cap) in topic_fill.items()),
        ]
        queries = [*self.namespace["genie_examples"].values(), *self.namespace["genie_benchmarks"].values()]
        self.assertEqual(len(queries), 6)
        for query, gold in zip(queries, expected, strict=True):
            with self.subTest(sql=query):
                self.assertEqual(self.values(query), gold)
                self.assertNotIn("IDENTIFIER(", query)
                self.assertIn(self.course.t("event_metrics"), query)
        self.assertTrue(set(queries[:3]).isdisjoint(queries[3:]))

    def test_exercises_correct_but_row_counts_and_unweighted_averages_fail(self):
        self.run_lesson()
        for exercise, wrong in [
            ("3.1", """SELECT city, count(*) FROM event_metrics
WHERE event_status = 'scheduled' GROUP BY city ORDER BY city"""),
            ("3.2", """SELECT topic, sum(feedback_count), round(avg(average_rating), 2) FROM event_metrics
WHERE event_status = 'completed' GROUP BY topic ORDER BY topic"""),
        ]:
            with self.subTest(exercise=exercise), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(self.course.check(exercise, EXERCISES[exercise]["solution"]))
                self.course.test_with_solutions = False
                self.assertFalse(self.course.check(exercise, wrong))

    def test_empty_cancelled_unknown_and_multi_child_edge_cases(self):
        self.run_lesson()
        # Reuse source schemas but replace only this in-memory test database's contents.
        for key in ["events", "bookings", "feedback"]:
            self.spark.db.execute(f"DELETE FROM {key}")
        events = []
        for eid, status, capacity in [("empty", "completed", 10), ("future", "scheduled", 20),
                                      ("mixed", "completed", 10), ("zero", "completed", 0)]:
            event = dict(self.events[0], event_id=eid, status=status, capacity=capacity)
            self.spark.db.execute("INSERT INTO events VALUES (" + ",".join("?" for _ in event) + ")",
                                  tuple(event.values()))
            events.append(event)
        bookings = []
        for eid, tickets, status, attended in [
            ("future", 3, "confirmed", None), ("mixed", 2, "confirmed", True),
            ("mixed", 3, "confirmed", False), ("mixed", 4, "confirmed", None),
            ("mixed", 7, "cancelled", True), ("empty", 1, "cancelled", False),
        ]:
            booking = dict(self.bookings[0], booking_id=f"edge{len(bookings)}", event_id=eid,
                           tickets=tickets, status=status, attended=attended)
            self.spark.db.execute("INSERT INTO bookings VALUES (" + ",".join("?" for _ in booking) + ")",
                                  tuple(booking.values()))
            bookings.append(booking)
        feedback = []
        for eid, rating in [("mixed", 1), ("mixed", 5), ("mixed", 3), ("zero", 4)]:
            response = dict(self.feedback[0], feedback_id=f"edge{len(feedback)}", event_id=eid, rating=rating)
            self.spark.db.execute("INSERT INTO feedback VALUES (" + ",".join("?" for _ in response) + ")",
                                  tuple(response.values()))
            feedback.append(response)
        expected = independent_metrics(events, bookings, feedback)
        for row in self.spark.table(self.course.t("event_metrics")).rows:
            with self.subTest(event=row["event_id"]):
                self.assertEqual(list(row), expected[row["event_id"]])
        mixed = dict(self.spark.sql("SELECT * FROM event_metrics WHERE event_id = 'mixed'").first())
        self.assertEqual((mixed["confirmed_tickets"], mixed["known_outcome_tickets"],
                          mixed["attended_tickets"], mixed["attendance_rate"]), (9, 5, 2, 0.4))
        self.assertEqual((mixed["feedback_count"], mixed["average_rating"]), (3, 3.0))
        self.assertIsNone(self.spark.sql("SELECT fill_rate FROM event_metrics WHERE event_id = 'zero'").first()[0])

    def test_reporting_projection_has_no_personal_fields_or_free_text(self):
        self.run_lesson()
        prohibited = {"customer_name", "customer_email", "booking_id", "feedback_id", "comment", "organisation_type"}
        self.assertTrue(prohibited.isdisjoint(self.spark.table(self.course.t("event_metrics")).columns))
        self.assertTrue(prohibited.isdisjoint(self.spark.sql(self.namespace["dashboard_sql"]).columns))
        instructions = self.namespace["genie_instructions"]
        self.assertIn(self.course.t("event_metrics"), instructions)
        self.assertNotIn(self.course.t("bookings"), instructions)

    def test_notebook_has_only_the_contracted_write_and_no_network_or_automatic_ui_claims(self):
        tree = ast.parse(SOURCE)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        self.assertEqual(imports, {"json", "WorkspaceClient"})
        self.run_lesson()
        writes = [query for query in self.spark.statements
                  if re.match(r"\s*(?:CREATE|DROP|ALTER|INSERT|UPDATE|DELETE)\b", query)]
        self.assertEqual(len(writes), 1)
        self.assertTrue(writes[0].startswith(f"CREATE OR REPLACE VIEW {self.course.t('event_metrics')}"))
        self.assertNotIn("A8.next_step(", SOURCE)  # UI completion requires observed evidence, not a green cell.
        self.assertIn("does **not** delete dashboards, Genie spaces", SOURCE)
        self.assertEqual(OBJECTS["event_metrics"], ("view", "03_descriptive_analytics"))
        self.assertIn("B1–B3", SOURCE)
        self.assertIn("View not created", SOURCE)

    def test_dashboard_file_reads_only_the_view_and_binds_real_fields(self):
        self.run_lesson()
        written = json.loads(self.dashboard_file.read_text(encoding="utf-8"))
        self.assertEqual(written, self.namespace["dashboard"])
        (dataset,) = written["datasets"]
        self.assertEqual("".join(dataset["queryLines"]), self.namespace["dashboard_sql"])
        sql = "".join(dataset["queryLines"])
        others = [self.course.t(k) for k in OBJECTS if k != "event_metrics"]
        self.assertFalse([name for name in others if name in sql])
        columns = set(self.spark.sql(sql).columns)
        layout = written["pages"][0]["layout"]
        kinds = {}
        for item in layout:
            widget = item["widget"]
            queries = {q["name"]: q["query"] for q in widget.get("queries", [])}
            for query in queries.values():
                self.assertEqual(query["datasetName"], dataset["name"])
                for field in query["fields"]:
                    if "associative_filter_predicate_group" in field["expression"]:
                        continue
                    used = set(re.findall(r"`([^`]+)`", field["expression"])) - {"associative_filter_predicate_group"}
                    self.assertTrue(used and used <= columns, field)
            if "spec" in widget:
                kinds.setdefault(widget["spec"]["widgetType"], []).append(widget)
                for enc in widget["spec"]["encodings"].get("fields", []):
                    self.assertIn(enc["queryName"], queries)
        self.assertEqual({k: len(v) for k, v in kinds.items()},
                         {"filter-single-select": 2, "filter-date-range-picker": 1, "counter": 2, "bar": 2, "table": 1})
        filtered = {w["spec"]["encodings"]["fields"][0]["fieldName"] for k in kinds if k.startswith("filter")
                    for w in kinds[k]}
        self.assertEqual(filtered, {"city", "event_status", "event_date"})
        counters = {w["queries"][0]["query"]["fields"][0]["expression"] for w in kinds["counter"]}
        self.assertEqual(counters, {"COUNT(`event_id`)", "SUM(`confirmed_tickets`)"})
        status = self.workspace.return_value.workspace.get_status
        status.assert_called_once_with(str(self.dashboard_file).removeprefix("/Workspace"))

    def test_dashboard_template_is_not_itself_a_dashboard_and_has_no_names(self):
        template = ROOT / "dashboards/event_snapshot.lvdash.template.json"
        self.assertFalse(template.name.endswith(".lvdash.json"))
        data = json.loads(template.read_text(encoding="utf-8"))
        self.assertEqual(data["datasets"][0]["queryLines"], [])
        self.assertNotIn("a8_", template.read_text(encoding="utf-8"))
        self.assertFalse(list(ROOT.rglob("*.lvdash.json")))

    def test_dashboard_file_default_no_and_never_overwrites(self):
        self.run_lesson(gates={"write_dashboard_file": False})
        self.assertFalse(self.dashboard_file.exists())
        self.workspace.return_value.workspace.get_status.assert_not_called()
        self.dashboard_file.write_text("learner edits", encoding="utf-8")
        self.run_lesson()
        self.assertEqual(self.dashboard_file.read_text(encoding="utf-8"), "learner edits")

    def test_dashboard_path_is_in_the_learners_own_folder(self):
        self.assertEqual(self.course.dashboard_path.as_posix(),
                         "/Workspace/Users/synthetic@example.com/a8learn/A8 offline8 event snapshot.lvdash.json")


if __name__ == "__main__":
    unittest.main()
