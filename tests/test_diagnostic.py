"""Offline execution of Module 4's real SQL and permutation test, checked against independent Python.

SQLite exercises the relational logic only, not Spark/Unity Catalog or the Genie/dashboard UI.
The event_metrics table is built from the shipped CSVs by a separate Python aggregation, not by Module 3's SQL.
"""
import ast
import contextlib
import io
import itertools
import random
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
from test_descriptive import FIELDS, OfflineSpark, Result, independent_metrics, read_fixture

NOTEBOOK = ROOT / "notebooks/04_diagnostic_analytics.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")


class PandasResult(Result):
    def toPandas(self):
        return pd.DataFrame([tuple(row) for row in self.rows], columns=self.columns)


class DiagnosticSpark(OfflineSpark):
    def sql(self, statement):
        base = super().sql(statement)
        wrapped = PandasResult.__new__(PandasResult)
        wrapped.columns, wrapped.rows = base.columns, base.rows
        return wrapped


def kitagawa(rows, weight, total):
    """Independent two-segment mix/rate split over topics, from plain Python dictionaries."""
    cells = defaultdict(lambda: [0, 0])
    for row in rows:
        if row["event_status"] != "completed":
            continue
        cell = cells[("online" if row["format"] == "online" else "other", row["topic"])]
        cell[0] += row[weight]
        cell[1] += row[total] or 0
    totals = {seg: sum(v[0] for (s, _), v in cells.items() if s == seg) for seg in ("online", "other")}
    mix = rate = 0.0
    for topic in {t for _, t in cells}:
        ow, pw = cells[("online", topic)][0] / totals["online"], cells[("other", topic)][0] / totals["other"]
        orate = cells[("online", topic)][1] / cells[("online", topic)][0]
        prate = cells[("other", topic)][1] / cells[("other", topic)][0]
        mix += (ow - pw) * (orate + prate) / 2
        rate += (orate - prate) * (ow + pw) / 2
    return mix, rate


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline8", "synthetic@example.com", "https://example.com"),
                             answers="solutions")
        self.spark = DiagnosticSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        events, bookings, feedback = [read_fixture(k) for k in ("events", "bookings", "feedback")]
        metrics = independent_metrics(events, bookings, feedback)
        self.rows = [dict(zip(FIELDS, v, strict=True)) for v in metrics.values()]
        self.spark.db.execute(f"CREATE TABLE event_metrics ({', '.join(FIELDS)})")
        self.spark.db.executemany(f"INSERT INTO event_metrics VALUES ({','.join('?' for _ in FIELDS)})",
                                  [tuple(r[f] for f in FIELDS) for r in self.rows])
        self.namespace = {"A8": self.course, "spark": self.spark, "display": lambda frame: frame.collect(),
                          "ROOT": ROOT}

    def run_lesson(self, exists=lambda key: True):
        with patch.object(self.course, "exists", side_effect=exists), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), self.namespace)

    def completed(self):
        return [r for r in self.rows if r["event_status"] == "completed"]

    def test_full_notebook_and_both_exercises_run_with_solutions(self):
        self.run_lesson()
        self.assertTrue(self.course.test_with_solutions)
        self.assertEqual(len(self.namespace["events_frame"]), 48)
        self.assertEqual(int(self.namespace["events_frame"]["is_online"].sum()), 15)

    def test_missing_view_stops_before_any_query(self):
        with self.assertRaisesRegex(RuntimeError, "Missing prerequisites: a8_offline8_event_metrics"):
            self.run_lesson(exists=lambda key: key != "event_metrics")
        self.assertEqual(self.spark.statements, [])

    def test_drill_downs_match_independent_aggregation(self):
        self.run_lesson()
        keys = {"city": lambda r: r["city"], "topic": lambda r: r["topic"], "format": lambda r: r["format"],
                "month": lambda r: r["event_date"][:7]}
        for dimension, key in keys.items():
            groups = defaultdict(list)
            for row in self.completed():
                groups[key(row)].append(row)
            expected = []
            for segment, items in sorted(groups.items()):
                known = sum(r["known_outcome_tickets"] for r in items)
                attended = sum(r["attended_tickets"] or 0 for r in items)
                feedback = sum(r["feedback_count"] for r in items)
                ratings = sum(r["rating_sum"] for r in items)
                expected.append((segment, len(items), known,
                                 round(100 * attended / known, 1) if known else None, feedback,
                                 round(ratings / feedback, 2) if feedback else None))
            with self.subTest(dimension=dimension):
                actual = [tuple(r) for r in self.spark.sql(self.namespace["drill_down_sql"](dimension)).rows]
                self.assertEqual(len(actual), len(expected))
                for got, want in zip(actual, expected, strict=True):
                    self.assertEqual(got[:3], want[:3])
                    self.assertAlmostEqual(got[3] or 0, want[3] or 0, delta=0.11)
                    self.assertEqual(got[4], want[4])
                    self.assertAlmostEqual(got[5] or 0, want[5] or 0, delta=0.011)

    def test_unknown_dimension_is_rejected(self):
        self.run_lesson()
        with self.assertRaises(AssertionError):
            self.namespace["drill_down_sql"]("customer_email")

    def test_mix_and_rate_split_matches_independent_python_and_adds_up(self):
        self.run_lesson()
        for weight, total, scale, digits, sql in [
            ("known_outcome_tickets", "attended_tickets", 100, 1, self.namespace["attendance_total_sql"]),
            ("feedback_count", "rating_sum", 1, 2, self.namespace["decomposition_sql"](
                "feedback_count", "rating_sum", 1, 2, False)),
        ]:
            mix, rate = kitagawa(self.completed(), weight, total)
            row = self.spark.sql(sql).first()
            with self.subTest(weight=weight):
                self.assertAlmostEqual(row["mix_effect"], scale * mix, places=digits)
                self.assertAlmostEqual(row["rate_effect"], scale * rate, places=digits)
                self.assertAlmostEqual(row["total_gap"], scale * (mix + rate), places=digits)
        by_topic = self.spark.sql(self.namespace["attendance_by_topic_sql"]).rows
        self.assertEqual([r["topic"] for r in by_topic], ["AI", "Analytics", "Data engineering", "Leadership"])
        self.assertAlmostEqual(sum(r["mix_effect"] + r["rate_effect"] for r in by_topic),
                               self.namespace["overall_gap"], delta=0.3)

    def test_the_mix_effect_is_not_the_whole_story_on_this_data(self):
        mix, rate = kitagawa(self.completed(), "known_outcome_tickets", "attended_tickets")
        self.assertLess(mix + rate, 0)
        self.assertGreater(abs(rate), abs(mix))

    def test_permutation_test_matches_independent_implementation(self):
        self.run_lesson()
        frame = self.namespace["events_frame"]
        known, attended, online = frame["known"].tolist(), frame["attended"].tolist(), frame["is_online"].tolist()

        def gap(flags):
            on = [i for i, f in enumerate(flags) if f]
            off = [i for i, f in enumerate(flags) if not f]
            return (sum(attended[i] for i in on) / sum(known[i] for i in on)
                    - sum(attended[i] for i in off) / sum(known[i] for i in off))

        observed = gap(online)
        self.assertAlmostEqual(self.namespace["observed_gap"], observed, places=12)
        rng = random.Random(7)
        shuffled, count, runs = list(online), 0, 20000
        for _ in range(runs):
            rng.shuffle(shuffled)
            count += abs(gap(shuffled)) >= abs(observed) - 1e-12
        self.assertAlmostEqual(self.namespace["p_value"], (count + 1) / (runs + 1), delta=0.01)
        self.assertLess(self.namespace["p_value"], 0.05)

    def test_permutation_test_is_seeded_and_matches_exact_enumeration(self):
        self.run_lesson()
        test = self.namespace["permutation_test"]
        known, attended, flags = [10, 20, 30, 15, 25, 40], [9, 15, 12, 14, 10, 38], [1, 1, 1, 0, 0, 0]
        self.assertEqual(test(known, attended, flags, 2000, seed=5), test(known, attended, flags, 2000, seed=5))

        def gap(chosen):
            on = set(chosen)
            return (sum(attended[i] for i in on) / sum(known[i] for i in on)
                    - sum(attended[i] for i in range(6) if i not in on)
                    / sum(known[i] for i in range(6) if i not in on))

        observed = gap((0, 1, 2))
        exact = sum(abs(gap(c)) >= abs(observed) - 1e-12 for c in itertools.combinations(range(6), 3)) / 20
        got_gap, got_p = test(known, attended, flags, 30000, seed=11)
        self.assertAlmostEqual(got_gap, observed, places=12)
        self.assertAlmostEqual(got_p, exact, delta=0.02)
        self.assertTrue(0 < exact < 1)

    def test_exercise_solutions_pass_and_naive_answers_fail(self):
        self.run_lesson()
        wrong = {
            "4.1": """SELECT topic, round(100.0 * (avg(CASE WHEN format = 'online' THEN attendance_rate END)
- avg(CASE WHEN format <> 'online' THEN attendance_rate END)), 1) AS gap_pp
FROM event_metrics WHERE event_status = 'completed' GROUP BY topic ORDER BY topic""",
            "4.2": """SELECT 0.0 AS mix_effect, round(avg(CASE WHEN format = 'online' THEN average_rating END)
- avg(CASE WHEN format <> 'online' THEN average_rating END), 2) AS rate_effect, 0.0 AS total_gap
FROM event_metrics WHERE event_status = 'completed'""",
        }
        for exercise, query in wrong.items():
            with self.subTest(exercise=exercise), contextlib.redirect_stdout(io.StringIO()):
                self.course.test_with_solutions = True
                self.assertTrue(self.course.check(exercise, EXERCISES[exercise]["solution"]))
                self.course.test_with_solutions = False
                self.assertFalse(self.course.check(exercise, query))
                self.assertFalse(self.course.check(exercise, ""))

    def test_notebook_reads_only_and_states_the_causation_limit(self):
        imports = {alias.name for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        self.assertEqual(imports, {"numpy"})
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(SOURCE))))
        self.run_lesson()
        self.assertFalse([q for q in self.spark.statements
                          if q.lstrip().upper().startswith(("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE"))])
        for forbidden in ("saveAsTable", ".write", "A8.gate", "write_text", "A8.guard"):
            self.assertNotIn(forbidden, SOURCE)
        self.assertIn("Nothing in this notebook proves\n# MAGIC causation", SOURCE)
        self.assertIn("**Where this sits:**", SOURCE)

    def test_course_navigation_points_to_module_1c(self):
        descriptive = (ROOT / "notebooks/03_descriptive_analytics.py").read_text(encoding="utf-8")
        self.assertIn("04_diagnostic_analytics", descriptive)
        index = (ROOT / "docs/index.md").read_text(encoding="utf-8")
        self.assertIn("| 4. Diagnostic analytics |", index)
        self.assertIn("04_diagnostic_analytics", index)
        self.assertIn("04_diagnostic_analytics", (ROOT / "START_HERE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
