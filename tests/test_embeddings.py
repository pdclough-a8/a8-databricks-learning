"""Offline checks for Module 8a. No model is ever called: ai_query is replaced by a deterministic stand-in.

SQLite runs the plain SQL and exercises only. Whether the embedding endpoint exists, its quota, or how meaningful real
embeddings are is not tested here.
"""
import ast
import contextlib
import io
import sys
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
from a8learn import Config, Course
from a8learn.exercises import EXERCISES
from test_descriptive import OfflineSpark, read_fixture

NOTEBOOK = ROOT / "notebooks/08a_embeddings.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
KEYWORDS = ("stream", "audio")


class Row(dict):
    pass


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows


class StandInSpark(OfflineSpark):
    """Plain SQL goes to SQLite. ai_query is recorded and answered with a hash-seeded vector, no model."""

    def __init__(self, course):
        super().__init__(course)
        self.ai_statements = []

    def sql(self, statement, args=None):
        if "ai_query" in statement:
            self.statements.append(statement)
            self.ai_statements.append((statement, args))
            texts = [v for _, v in sorted(args.items(), key=lambda kv: int(kv[0][1:]))]
            return Rows([Row(text=t, embedding=list(np.random.default_rng(zlib.crc32(t.encode())).normal(size=8)))
                         for t in texts])
        return super().sql(statement)


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline8", "synthetic@example.com", "https://example.com"),
                             answers="solutions")
        self.spark = StandInSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.feedback = read_fixture("feedback")
        self.spark.load("feedback", self.feedback)
        self.spark.load("events", read_fixture("events"))

    def run_lesson(self, approve=False):
        class Dbutils:
            pass

        self.sdk_calls = []

        def query(name, input):
            """Stands in for serving_endpoints.query: same vectors as the SQL stand-in, returned out of order."""
            self.sdk_calls.append((name, list(input)))
            vectors = [np.random.default_rng(zlib.crc32(t.encode())).normal(size=8) for t in input]
            return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=list(v))
                                         for i, v in reversed(list(enumerate(vectors)))])

        fake_client = SimpleNamespace(serving_endpoints=SimpleNamespace(query=query))

        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        with patch.object(self.course, "require"), patch("databricks.sdk.WorkspaceClient", return_value=fake_client), \
             patch.object(self.course, "gate", lambda name, label: approve), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    def test_default_run_calls_no_model_and_writes_nothing(self):
        namespace = self.run_lesson()
        self.assertEqual(self.spark.ai_statements, [])
        self.assertIsNone(namespace["embeddings"])
        writes = ("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE")
        self.assertFalse([q for q in self.spark.statements if q.lstrip().upper().startswith(writes)])
        self.assertIn("Embedding skipped", self.output)
        self.assertEqual(self.sdk_calls, [])
        self.assertIsNone(namespace["python_vectors"])

    def test_python_route_sends_the_same_texts_through_the_sdk_and_matches_sql(self):
        namespace = self.run_lesson(approve=True)
        self.assertEqual(len(self.sdk_calls), 1)
        name, texts = self.sdk_calls[0]
        self.assertEqual(name, "databricks-gte-large-en")
        self.assertEqual(texts, namespace["texts"])
        self.assertEqual(len(self.spark.ai_statements), 1)  # the SQL route still sends one query
        self.assertEqual(set(namespace["python_vectors"]), set(texts))
        self.assertIn("Lowest similarity between the two routes", self.output)

    def test_distinct_comments_cover_every_feedback_row(self):
        namespace = self.run_lesson()
        self.assertEqual(set(namespace["comments"]), {r["comment"] for r in self.feedback})
        self.assertEqual(sum(namespace["counts"]), len(self.feedback))

    def test_bag_of_words_misses_the_audio_complaint(self):
        namespace = self.run_lesson()
        query = "The stream kept buffering."
        top = namespace["most_similar"](namespace["count_vector"](query), namespace["toy_vectors"], k=1, skip=query)
        self.assertEqual(top[0][1], "Stream quality was excellent.")
        audio = namespace["count_vector"]("Audio dropped out several times online.")
        self.assertEqual(namespace["cosine"](namespace["count_vector"](query), audio), 0.0)

    def test_keyword_search_finds_exact_words_only(self):
        keyword = self.run_lesson()["keyword_search"]
        self.assertEqual(len(keyword("food")), 0)
        self.assertEqual(len(keyword("AUDIO")), 1)

    def test_approved_run_sends_thirty_texts_once_and_nothing_else(self):
        namespace = self.run_lesson(approve=True)
        self.assertEqual(len(self.spark.ai_statements), 1)
        statement, args = self.spark.ai_statements[0]
        self.assertEqual(len(args), 30)
        self.assertEqual(set(args.values()), set(namespace["comments"]) | set(namespace["probes"]))
        self.assertIn("'databricks-gte-large-en'", statement)
        for text in args.values():
            self.assertNotIn(text, statement)  # text travels as a parameter
        self.assertEqual(len(namespace["embeddings"]), 30)
        self.assertIn("feedback rows, average rating", self.output)

    def test_exercise_solutions_match_independent_python(self):
        self.run_lesson()
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["8a.1"]["solution"]).collect()]
        counts = {}
        for r in self.feedback:
            if any(w in r["comment"].lower() for w in KEYWORDS):
                counts[r["comment"]] = counts.get(r["comment"], 0) + 1
        self.assertEqual(rows, sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        formats = {r["event_id"]: r["format"] for r in read_fixture("events")}
        per_event = {}
        for r in self.feedback:
            if formats[r["event_id"]] == "online" and any(w in r["comment"].lower() for w in KEYWORDS):
                per_event[r["event_id"]] = per_event.get(r["event_id"], 0) + 1
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["8a.2"]["solution"]).collect()]
        self.assertEqual(rows, sorted(per_event.items()))

    def test_blank_and_naive_exercise_answers_fail(self):
        self.run_lesson()
        naive = ("SELECT comment, count(*) AS rows FROM IDENTIFIER(a8_feedback) WHERE comment LIKE '%stream%' "
                 "GROUP BY comment ORDER BY rows DESC, comment")
        self.course.test_with_solutions = False
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("8a.1", ""))
            self.assertFalse(self.course.check("8a.1", naive))

    def test_notebook_standard_and_scope(self):
        tree = ast.parse(SOURCE)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for forbidden in ("saveAsTable", ".write", "A8.guard", "A8.run", "A8.sql", "mlflow", "CREATE ", "INSERT "):
            self.assertNotIn(forbidden, SOURCE)
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "validated live"):
            self.assertIn(phrase, text)
        self.assertIn('A8.gate("embed_comments"', SOURCE)

    def test_navigation_mentions_module_8a(self):
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/07_genai.py"):
            self.assertIn("08a_embeddings", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 8a", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
