"""Offline checks for Module 7. No model is ever called: AI Functions are replaced by a deterministic stand-in.

SQLite runs the bounded sample and exercise SQL only. Whether real AI Functions are available, priced or accurate on a
workspace is not tested here. Widgets are simulated so one-use approval can be exercised.
"""
import ast
import contextlib
import io
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
from a8learn import Config, Course
from a8learn.exercises import EXERCISES
from test_descriptive import OfflineSpark, read_fixture

NOTEBOOK = ROOT / "notebooks/07_genai.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")


class Row(dict):
    def asDict(self):
        return dict(self)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows


class StandInSpark(OfflineSpark):
    """Plain SQL goes to SQLite. AI statements are recorded and answered without any model."""

    def __init__(self, course):
        super().__init__(course)
        self.ai_statements = []

    def sql(self, statement, args=None):
        if "ai_analyze_sentiment" in statement or "ai_query" in statement:
            self.statements.append(statement)
            self.ai_statements.append((statement, args))
            if "ai_query" in statement:
                return Rows([Row(response="stand-in observation")])
            comments = [v for k, v in sorted(args.items()) if k.startswith("comment")]
            return Rows([Row(comment=c, sentiment="neutral", classification="stand-in") for c in comments])
        base = super().sql(statement)
        if "SELECT feedback_id, rating, comment" in statement:
            return Rows([Row(zip(base.columns, r, strict=True)) for r in base.rows])
        return base


class FakeWidgets:
    def __init__(self, approvals):
        self.values, self.approvals = {}, approvals

    def create(self, name):
        self.values[name] = self.approvals.get(name, "no")

    def get(self, name):
        return self.values[name]

    def remove(self, name):
        del self.values[name]


class GenAITests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline8", "synthetic@example.com", "https://example.com"),
                             answers="solutions")
        self.spark = StandInSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.feedback = read_fixture("feedback")
        self.spark.load("feedback", self.feedback)

    def run_lesson(self, approvals=None, source=SOURCE):
        widgets = FakeWidgets(approvals or {})
        self.widgets = widgets

        class Dbutils:
            pass

        Dbutils.widgets = widgets
        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT}

        def gate(name, _label):
            widgets.create(name)
            return widgets.get(name) == "yes"

        with patch.object(self.course, "exists", return_value=True), patch.object(self.course, "gate", gate), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(source, str(NOTEBOOK), "exec"), namespace)
        self.namespace, self.output = namespace, out.getvalue()
        return namespace

    def test_default_run_makes_no_ai_request_and_writes_nothing(self):
        namespace = self.run_lesson()
        self.assertEqual(self.spark.ai_statements, [])
        self.assertEqual(namespace["task_results"], [])
        self.assertEqual(namespace["query_results"], [])
        self.assertFalse([q for q in self.spark.statements
                          if q.lstrip().upper().startswith(("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE"))])

    def test_sample_is_five_ordered_non_empty_comments(self):
        sample = self.run_lesson()["sample"]
        expected = sorted((r for r in self.feedback if (r["comment"] or "").strip()),
                          key=lambda r: r["feedback_id"])[:5]
        self.assertEqual([r["feedback_id"] for r in sample], [r["feedback_id"] for r in expected])
        self.assertLessEqual(len(sample), 5)

    def test_approved_tasks_run_once_with_bounded_parameterised_input(self):
        source = SOURCE.replace('TASK_APPROVAL_NOTE = ""', 'TASK_APPROVAL_NOTE = "offline note"')
        namespace = self.run_lesson({"genai_tasks": "yes"}, source)
        self.assertEqual(len(self.spark.ai_statements), 1)
        statement, args = self.spark.ai_statements[0]
        self.assertEqual(len(namespace["task_results"]), len(namespace["sample"]))
        self.assertNotIn("genai_tasks", self.widgets.values)  # one-use: consumed
        for row in namespace["sample"]:
            self.assertNotIn(row["comment"], statement)  # comment text travels as a parameter
        self.assertIn("'2.1'", statement)

    def test_approval_without_a_note_is_refused_before_any_request(self):
        with self.assertRaises(AssertionError):
            self.run_lesson({"genai_tasks": "yes"})
        self.assertEqual(self.spark.ai_statements, [])

    def test_ai_query_needs_databricks_endpoint_note_and_its_own_approval(self):
        with self.assertRaises(AssertionError):
            self.run_lesson({"genai_query": "yes"})
        self.assertEqual(self.spark.ai_statements, [])
        source = SOURCE.replace('CHAT_ENDPOINT = ""', 'CHAT_ENDPOINT = "databricks-example"').replace(
            'QUERY_APPROVAL_NOTE = ""', 'QUERY_APPROVAL_NOTE = "offline note"')
        namespace = self.run_lesson({"genai_query": "yes"}, source)
        self.assertEqual(len(self.spark.ai_statements), 1)
        self.assertEqual(len(namespace["query_results"]), 1)
        self.assertNotIn("genai_query", self.widgets.values)
        self.assertEqual(namespace["task_results"], [])  # task gate stayed closed

    def test_exercise_solutions_match_independent_python(self):
        self.run_lesson()
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["7.1"]["solution"]).collect()]
        keep = sorted((r for r in self.feedback if (r["comment"] or "").strip()), key=lambda r: r["feedback_id"])[:5]
        self.assertEqual(rows, [(r["feedback_id"], len(r["comment"])) for r in keep])
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["7.2"]["solution"]).collect()]
        self.assertEqual(rows, [(2, "disagree"), (4, "review"), (5, "review")])

    def test_naive_and_blank_exercise_answers_fail(self):
        self.run_lesson()
        naive = """WITH examples(example_id, rating, sentiment) AS (
VALUES (1,5,'positive'),(2,1,'positive'),(3,3,'neutral'),(4,4,'mixed'),(5,2,NULL),(6,2,'negative'))
SELECT example_id, 'disagree' AS review_reason FROM examples
WHERE sentiment <> CASE WHEN rating <= 2 THEN 'negative' WHEN rating = 3 THEN 'neutral' ELSE 'positive' END
ORDER BY example_id"""
        with contextlib.redirect_stdout(io.StringIO()):
            for exercise, query in [("7.1", EXERCISES["7.1"]["solution"]), ("7.2", EXERCISES["7.2"]["solution"])]:
                self.course.test_with_solutions = True
                self.assertTrue(self.course.check(exercise, query))
            self.course.test_with_solutions = False
            self.assertFalse(self.course.check("7.2", naive))
            self.assertFalse(self.course.check("7.1", ""))
            self.assertFalse(self.course.check("7.2", ""))

    def test_notebook_standard_scope_and_limits(self):
        tree = ast.parse(SOURCE)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in tree.body))
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for forbidden in ("saveAsTable", ".write", "write_text", "A8.guard", "A8.run", "A8.sql", "mlflow",
                          "CREATE ", "INSERT "):
            self.assertNotIn(forbidden, SOURCE)
        self.assertEqual(len(re.findall(r'A8\.gate\("genai_', SOURCE)), 2)
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free Edition first", "not a hard", "Checkpoint H1", "context, not RAG",
                       "Nothing here is live validated"):
            self.assertIn(phrase, text)
        for line in SOURCE.splitlines():
            if "ai_classify(" in line:
                self.assertIn("'2.1'", line)

    def test_course_navigation_mentions_module_7(self):
        self.assertIn("07_genai", (ROOT / "docs/index.md").read_text(encoding="utf-8"))
        self.assertIn("07_genai", (ROOT / "START_HERE.md").read_text(encoding="utf-8"))
        self.assertIn("07_genai", (ROOT / "notebooks/06_prescriptive_analytics.py").read_text(encoding="utf-8"))
        validation = (ROOT / "docs/validation.md").read_text(encoding="utf-8")
        self.assertIn("Module 7", validation)
        self.assertIn("not live validated", validation.lower())


if __name__ == "__main__":
    unittest.main()
