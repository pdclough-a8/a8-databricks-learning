"""Offline execution of Module 6's real SQL and decision code, checked against independent Python.

SQLite exercises the relational logic only, not Spark/Unity Catalog. The prediction table is synthetic and built by a
separate Python loop with two model versions, so the latest-score rule is exercised. The Module 5 view is built by
independent Python aggregation, not by 03's SQL. Decisions are checked against exact enumeration and brute force.
"""
import ast
import contextlib
import io
import itertools
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
from a8learn import Config, Course
from a8learn.exercises import EXERCISES
from test_descriptive import OfflineSpark, Result, read_fixture

NOTEBOOK = ROOT / "notebooks/06_prescriptive_analytics.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
FORECAST_FIELDS = ["event_id", "event_name", "event_date", "capacity", "confirmed_tickets", "expected_attendees"]


class PandasResult(Result):
    def first(self):
        return self.rows[0] if self.rows else None  # Spark returns None for an empty result

    def toPandas(self):
        return pd.DataFrame([tuple(row) for row in self.rows], columns=self.columns)


class PredictionSpark(OfflineSpark):
    def sql(self, statement, args=None):
        for name, value in (args or {}).items():
            statement = re.sub(rf":{name}\b", "'" + str(value).replace("'", "''") + "'", statement)
        base = super().sql(statement)
        wrapped = PandasResult.__new__(PandasResult)
        wrapped.columns, wrapped.rows = base.columns, base.rows
        return wrapped


def probability(index, version):
    """A fixed, model-free attendance probability so the oracle never shares code with the notebook."""
    return round(0.5 + ((index * 37 + version * 11) % 45) / 100, 4)


def exact_distribution(tickets, probs):
    """Exact turnout distribution by dynamic programming over bookings (independent of numpy and enumeration)."""
    dist = {0: 1.0}
    for t, p in zip(tickets, probs, strict=True):
        step = defaultdict(float)
        for total, weight in dist.items():
            step[total] += weight * (1 - p)
            step[total + t] += weight * p
        dist = step
    return dist


def exact_binomial(limit, p):
    dist = {0: 1.0}
    for _ in range(limit):
        step = defaultdict(float)
        for k, weight in dist.items():
            step[k] += weight * (1 - p)
            step[k + 1] += weight * p
        dist = step
    return dist


class PrescriptiveTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline8", "synthetic@example.com", "https://example.com"),
                             answers="solutions")
        self.spark = PredictionSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.events, self.bookings = read_fixture("events"), read_fixture("bookings")
        self.build_tables()
        self.namespace = {"A8": self.course, "spark": self.spark, "display": lambda frame: None, "ROOT": ROOT}

    def build_tables(self):
        scheduled = {e["event_id"]: e for e in self.events if e["status"] == "scheduled"}
        self.latest = []  # (booking_id, event_id, tickets, probability) of the newest score only
        rows = []
        for index, booking in enumerate(b for b in self.bookings if b["status"] == "confirmed"
                                        and b["event_id"] in scheduled):
            for version, scored_at in ((1, "2026-11-01 09:00:00"), (2, "2026-11-10 09:00:00")):
                rows.append((booking["booking_id"], booking["event_id"], booking["tickets"],
                             probability(index, version), str(version), scored_at))
            self.latest.append((booking["booking_id"], booking["event_id"], booking["tickets"],
                                probability(index, 2)))
        db = self.spark.db
        db.execute("CREATE TABLE attendance_predictions (booking_id TEXT, event_id TEXT, tickets INTEGER, "
                   "attendance_probability REAL, model_version TEXT, scored_at TEXT)")
        db.executemany("INSERT INTO attendance_predictions VALUES (?,?,?,?,?,?)", rows)
        db.execute(f"CREATE TABLE event_forecast ({', '.join(FORECAST_FIELDS)})")
        for eid, event in scheduled.items():
            mine = [r for r in self.latest if r[1] == eid]
            db.execute("INSERT INTO event_forecast VALUES (?,?,?,?,?,?)",
                       (eid, event["event_name"], event["event_date"], event["capacity"],
                        sum(r[2] for r in mine), sum(r[2] * r[3] for r in mine)))

    def run_lesson(self, source=SOURCE, exists=lambda key: True):
        with patch.object(self.course, "exists", side_effect=exists), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source, str(NOTEBOOK), "exec"), self.namespace)

    def event_bookings(self, event_id):
        return [r for r in self.latest if r[1] == event_id]

    def test_full_notebook_and_both_exercises_run_with_solutions(self):
        self.run_lesson()
        self.assertTrue(self.course.test_with_solutions)
        self.assertEqual(self.namespace["capacity"], 150)
        self.assertEqual(len(self.namespace["bookings_frame"]), len(self.event_bookings("E150")))

    def test_every_scheduled_event_runs_end_to_end(self):
        for event_id in sorted({r[1] for r in self.latest}):
            with self.subTest(event=event_id):
                self.setUp()
                self.run_lesson(SOURCE.replace('EVENT_ID = "E150"', f'EVENT_ID = "{event_id}"'))
                self.assertGreaterEqual(self.namespace["best_limit"], self.namespace["capacity"])

    def test_missing_prerequisites_stop_before_any_query(self):
        with self.assertRaisesRegex(RuntimeError, "Missing prerequisites: a8_offline8_event_forecast"):
            self.run_lesson(exists=lambda key: key != "event_forecast")
        self.assertEqual(self.spark.statements, [])

    def test_completed_or_unknown_event_is_rejected(self):
        for bad in ("E101", "E999"):
            with self.subTest(event=bad), self.assertRaises(AssertionError):
                self.setUp()
                self.run_lesson(SOURCE.replace('EVENT_ID = "E150"', f'EVENT_ID = "{bad}"'))

    def test_event_id_is_a_parameter_not_interpolated_sql(self):
        self.run_lesson()
        queries = [q for q in self.spark.statements if "event_id = " in q and "E150" in q]
        self.assertFalse([q for q in queries if "event_forecast" in q and "WHERE event_id = 'E150'" not in q])
        with self.assertRaises(AssertionError):
            self.setUp()
            self.run_lesson(SOURCE.replace('EVENT_ID = "E150"', "EVENT_ID = \"E150' OR '1'='1\""))

    def test_latest_scores_drive_the_catering_inputs(self):
        self.run_lesson()
        frame = self.namespace["bookings_frame"].sort_values("booking_id")
        expected = sorted((b, t, p) for b, e, t, p in self.event_bookings("E150"))
        self.assertEqual(list(frame["booking_id"]), [x[0] for x in expected])
        for got, want in zip(frame["attendance_probability"], expected, strict=True):
            self.assertAlmostEqual(got, want[2], places=9)

    def test_overbooking_best_limit_matches_brute_force_over_exact_costs(self):
        self.run_lesson()
        capacity, p = self.namespace["capacity"], self.namespace["show_probability"]
        c_turn, c_empty = self.namespace["COSTS"]["turned_away"], self.namespace["COSTS"]["empty_seat"]

        def exact_cost(limit):
            return sum(w * (c_turn * max(k - capacity, 0) + c_empty * max(capacity - k, 0))
                       for k, w in exact_binomial(limit, p).items())

        costs = {limit: exact_cost(limit) for limit in range(capacity, int(1.5 * capacity) + 1)}
        brute = min(costs, key=costs.get)
        chosen = int(self.namespace["best_limit"])
        # Simulation noise can pick a neighbour of a very flat minimum; its true cost must still be near-optimal.
        self.assertLessEqual(costs[chosen], costs[brute] * 1.01)
        self.assertLessEqual(abs(chosen - brute), 8)
        self.assertGreaterEqual(chosen, capacity)
        self.assertAlmostEqual(self.namespace["exact_overbooking_cost"](chosen, capacity, p, c_turn, c_empty),
                               costs[chosen], places=6)

    def test_overbooking_limit_moves_the_right_way_with_costs(self):
        self.run_lesson()
        optimise = self.namespace["optimise_overbooking"]
        cheap = optimise(100, 0.75, 15.0, 15.0)[2]
        dear = optimise(100, 0.75, 120.0, 15.0)[2]
        self.assertGreater(cheap, dear)
        self.assertGreater(dear, 100)
        self.assertGreater(optimise(100, 0.75, 60.0, 15.0)[2], optimise(100, 0.95, 60.0, 15.0)[2])

    def test_turnout_simulation_matches_exact_enumeration_on_a_small_case(self):
        self.run_lesson()
        import numpy as np
        tickets, probs = [1.0, 2.0, 3.0, 1.0], [0.9, 0.6, 0.5, 0.2]
        outcomes = defaultdict(float)
        for shows in itertools.product((0, 1), repeat=4):
            weight = 1.0
            for show, p in zip(shows, probs, strict=True):
                weight *= p if show else 1 - p
            outcomes[sum(t for show, t in zip(shows, tickets, strict=True) if show)] += weight
        self.assertEqual(outcomes.keys(), exact_distribution([1, 2, 3, 1], probs).keys())
        simulated = self.namespace["simulate_turnout"](np.array(tickets), np.array(probs), 60000, 3)
        for total, weight in outcomes.items():
            self.assertAlmostEqual((simulated == total).mean(), weight, delta=0.01)
        self.assertEqual(list(self.namespace["simulate_turnout"](np.array(tickets), np.array(probs), 50, 9)),
                         list(self.namespace["simulate_turnout"](np.array(tickets), np.array(probs), 50, 9)))

    def test_catering_choice_matches_brute_force_over_the_exact_distribution(self):
        self.run_lesson()
        bookings = self.event_bookings("E150")
        tickets, probs = [b[2] for b in bookings], [b[3] for b in bookings]
        dist = exact_distribution(tickets, probs)
        short, waste = self.namespace["COSTS"]["short_meal"], self.namespace["COSTS"]["wasted_meal"]
        costs = {m: sum(w * (short * max(k - m, 0) + waste * max(m - k, 0)) for k, w in dist.items())
                 for m in range(sum(tickets) + 1)}
        brute = min(costs, key=costs.get)
        self.assertLessEqual(costs[self.namespace["best_meals"]], costs[brute] * 1.01 + 1e-9)
        self.assertLessEqual(abs(self.namespace["best_meals"] - brute), 2)
        mean = sum(k * w for k, w in dist.items())
        variance = sum((k - mean) ** 2 * w for k, w in dist.items())
        self.assertAlmostEqual(self.namespace["exact_mean"], mean, places=6)
        self.assertAlmostEqual(self.namespace["exact_variance"], variance, places=6)
        self.assertAlmostEqual(float(self.namespace["turnout"].mean()), mean, delta=0.5)

    def test_exercise_solutions_match_independent_python(self):
        self.run_lesson()
        by_event = defaultdict(list)
        for row in self.latest:
            by_event[row[1]].append(row)
        forecast = self.spark.sql("SELECT * FROM event_forecast ORDER BY event_id").rows
        for key, query in [("6.1", EXERCISES["6.1"]["solution"]), ("6.2", EXERCISES["6.2"]["solution"])]:
            sql = re.sub(r"IDENTIFIER\(a8_(\w+)\)", r"\1", query)
            result = self.spark.sql(sql).rows
            with self.subTest(exercise=key):
                if key == "6.1":
                    want = [(r["event_id"], round(r["expected_attendees"] / r["confirmed_tickets"], 3),
                             int(r["capacity"] / (r["expected_attendees"] / r["confirmed_tickets"])))
                            for r in forecast if r["expected_attendees"] > 0]
                    self.assertEqual([tuple(r) for r in result], want)
                else:
                    want = {e: round(sum(t * t * p * (1 - p) for _, _, t, p in rows), 2)
                            for e, rows in sorted(by_event.items())}
                    self.assertEqual([r[0] for r in result], list(want))
                    for row in result:
                        self.assertAlmostEqual(row[1], want[row[0]], delta=0.011)

    def test_naive_exercise_answers_fail_and_blank_answers_are_rejected(self):
        self.run_lesson()
        wrong = {
            "6.1": """SELECT event_id, round(expected_attendees / confirmed_tickets, 3) AS show_probability,
round(capacity / (expected_attendees / confirmed_tickets), 0) AS simple_limit
FROM event_forecast WHERE expected_attendees > 0 ORDER BY event_id""",
            "6.2": """SELECT event_id, round(sum(tickets * tickets * attendance_probability
* (1 - attendance_probability)), 2) AS attendance_variance
FROM attendance_predictions GROUP BY event_id ORDER BY event_id""",
        }
        for exercise, query in wrong.items():
            with self.subTest(exercise=exercise), contextlib.redirect_stdout(io.StringIO()):
                self.course.test_with_solutions = True
                self.assertTrue(self.course.check(exercise, EXERCISES[exercise]["solution"]))
                self.course.test_with_solutions = False
                self.assertFalse(self.course.check(exercise, query))
                self.assertFalse(self.course.check(exercise, ""))

    def test_notebook_is_read_only_and_states_its_limits(self):
        tree = ast.parse(SOURCE)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        self.assertEqual(imports, {"math", "numpy", "pandas"})
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        self.run_lesson()
        self.assertFalse([q for q in self.spark.statements
                          if q.lstrip().upper().startswith(("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE"))])
        for forbidden in ("saveAsTable", ".write", "A8.gate", "write_text", "A8.guard", "ai_query", "mlflow"):
            self.assertNotIn(forbidden, SOURCE)
        for phrase in ("**Where this sits:**", "assumed teaching parameters", "not a guarantee", "Independence",
                       "Humans decide", "Checkpoint H1"):
            self.assertIn(phrase, SOURCE.replace("# MAGIC ", ""))

    def test_course_navigation_and_branding_point_to_module_1d(self):
        index = (ROOT / "docs/index.md").read_text(encoding="utf-8")
        self.assertIn("| 6. Prescriptive analytics |", index)
        self.assertIn("06_prescriptive_analytics", index)
        self.assertNotIn("number to be assigned", index)
        self.assertIn("06_prescriptive_analytics", (ROOT / "START_HERE.md").read_text(encoding="utf-8"))
        logo = ROOT / "docs/assets/a8-logo.png"
        self.assertEqual(logo.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn("assets/a8-logo.png", (ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
        for page in ("README.md", "START_HERE.md", "docs/index.md"):
            self.assertIn("a8-logo.png", (ROOT / page).read_text(encoding="utf-8"), page)


if __name__ == "__main__":
    unittest.main()
