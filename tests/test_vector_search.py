"""Offline checks for Module 8c. The Databricks SDK's Vector Search classes are replaced by an in-memory stand-in.

Nothing here proves that a workspace can create an endpoint or index, how long that takes, or what it costs: that is
the live validation. These tests check the notebook's logic, its gates, the index definition and the cleanup order.
"""
import ast
import contextlib
import io
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
from a8learn import Config, Course
from a8learn.exercises import EXERCISES
from databricks.sdk.errors import NotFound
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    EndpointStatusState,
    EndpointType,
    PipelineType,
    VectorIndexType,
)
from test_descriptive import OfflineSpark

NOTEBOOK = ROOT / "notebooks/08c_vector_search.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
DOCS = sorted((ROOT / "data/docs").glob("*.md"))
COLUMNS = ["chunk_id", "doc_name", "doc_title", "section", "content"]
USER = "synthetic@example.com"


def chunk_rows():
    """Independent chunking of the shipped documents, as the table from 08b would hold it."""
    rows = []
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", text, re.M).group(1)
        parts = re.split(r"^## (.+)$", text, flags=re.M)
        for n, (heading, body) in enumerate(zip(parts[1::2], parts[2::2], strict=True), start=1):
            content = f"{title} - {heading}: {' '.join(body.split())}"
            rows.append((f"{path.stem}-{n}", path.name, title, heading, content))
    return rows


class FakeVectorSearch:
    """In-memory endpoints and indexes; records every call so tests can check order and arguments."""

    def __init__(self, rows, foreign_endpoint=False):
        self.rows, self.calls = rows, []
        self.endpoints, self.indexes = {}, {}
        if foreign_endpoint:
            self.endpoints["a8-offline8-vs"] = SimpleNamespace(creator="other@example.com", num_indexes=0)
        self.vector_search_endpoints = SimpleNamespace(
            get_endpoint=self.get_endpoint, create_endpoint=self.create_endpoint, delete_endpoint=self.delete_endpoint)
        self.vector_search_indexes = SimpleNamespace(
            get_index=self.get_index, create_index=self.create_index, query_index=self.query_index,
            delete_index=self.delete_index)

    def get_endpoint(self, name):
        if name not in self.endpoints:
            raise NotFound("no endpoint")
        info = self.endpoints[name]
        info.endpoint_status = SimpleNamespace(state=EndpointStatusState.ONLINE, message="")
        info.num_indexes = sum(1 for i in self.indexes.values() if i.endpoint_name == name)
        return info

    def create_endpoint(self, name, endpoint_type):
        self.calls.append(("create_endpoint", name, endpoint_type))
        self.endpoints[name] = SimpleNamespace(creator=USER, num_indexes=0)

    def delete_endpoint(self, name):
        self.calls.append(("delete_endpoint", name))
        del self.endpoints[name]

    def get_index(self, name):
        if name not in self.indexes:
            raise NotFound("no index")
        return self.indexes[name]

    def create_index(self, **kwargs):
        self.calls.append(("create_index", kwargs))
        self.indexes[kwargs["name"]] = SimpleNamespace(
            creator=USER, endpoint_name=kwargs["endpoint_name"],
            status=SimpleNamespace(ready=True, indexed_row_count=len(self.rows), message=""))

    def delete_index(self, name):
        self.calls.append(("delete_index", name))
        del self.indexes[name]

    def query_index(self, index_name, columns, query_text, num_results):
        self.calls.append(("query_index", query_text, num_results))
        asked = set(re.findall(r"[a-z]+", query_text.lower()))
        scored = sorted(((len(asked & set(re.findall(r"[a-z]+", r[4].lower()))), r) for r in self.rows),
                        key=lambda s: -s[0])[:num_results]
        return SimpleNamespace(result=SimpleNamespace(data_array=[list(r) + [float(score)] for score, r in scored]))


class StandInSpark(OfflineSpark):
    """Plain SQL goes to SQLite. The chat ai_query is recorded and answered without any model."""

    def __init__(self, course):
        super().__init__(course)
        self.chat_calls = []

    def sql(self, statement, args=None):
        if "ai_query" in statement:
            self.statements.append(statement)
            self.chat_calls.append((statement, args))
            count = len(args) // 2
            return SimpleNamespace(collect=lambda: [
                {"question": args[f"q{i}"], "reply": {"result": "Stand-in answer [1].", "errorMessage": None}}
                for i in range(count)])
        return super().sql(statement)


class FakeWidgets:
    def text(self, name, default, label):
        pass

    def get(self, name):
        return "10"


class VectorSearchTests(unittest.TestCase):
    def setUp(self):
        config = Config("workspace", "default", "offline8", USER, "https://example.com")
        self.course = Course(config, answers="solutions")
        self.spark = StandInSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.rows = chunk_rows()
        self.spark.db.execute(f"CREATE TABLE doc_chunks ({', '.join(c + ' TEXT' for c in COLUMNS)})")
        self.spark.db.executemany("INSERT INTO doc_chunks VALUES (?, ?, ?, ?, ?)", self.rows)

    def run_lesson(self, endpoint=False, index=False, ask=False, delete=False, foreign_endpoint=False):
        self.fake = FakeVectorSearch(self.rows, foreign_endpoint)

        class Dbutils:
            widgets = FakeWidgets()

        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        approvals = {"create_vs_endpoint": endpoint, "create_vs_index": index, "ask_model_vs": ask,
                     "delete_vector_search": delete}
        with patch("databricks.sdk.WorkspaceClient", return_value=self.fake), \
             patch.object(self.course, "require"), patch("time.sleep"), \
             patch.object(self.course, "gate", lambda name, label: approvals[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    def test_default_run_creates_queries_and_deletes_nothing(self):
        self.run_lesson()
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.spark.chat_calls, [])
        self.assertIn("Index not created", self.output)
        self.assertIn("Not deleted. Remember: your endpoint bills", self.output)

    def test_full_run_creates_queries_answers_and_deletes_in_order(self):
        self.run_lesson(endpoint=True, index=True, ask=True, delete=True)
        names = [c[0] for c in self.fake.calls]
        self.assertEqual(names[:2], ["create_endpoint", "create_index"])
        self.assertEqual(names.count("create_endpoint"), 1)
        # 1 demo query, 8 questions at k=1, 8 at k=3, then 2 retrievals for the grounded answers.
        self.assertEqual(names.count("query_index"), 19)
        self.assertLess(names.index("delete_index"), names.index("delete_endpoint"))
        self.assertEqual((self.fake.endpoints, self.fake.indexes), ({}, {}))
        self.assertEqual(len(self.spark.chat_calls), 1)
        self.assertEqual(len(self.spark.chat_calls[0][1]), 4)
        self.assertIn("failOnError => false", self.spark.chat_calls[0][0])
        self.assertIn("Index:        hit@1", self.output)

    def test_index_definition_uses_the_chunk_table_and_embeds_content(self):
        self.run_lesson(endpoint=True, index=True)
        create_endpoint = next(c for c in self.fake.calls if c[0] == "create_endpoint")
        self.assertEqual(create_endpoint[1:], ("a8-offline8-vs", EndpointType.STANDARD))
        kwargs = next(c for c in self.fake.calls if c[0] == "create_index")[1]
        self.assertEqual(kwargs["name"], "workspace.default.a8_offline8_doc_index")
        self.assertEqual((kwargs["primary_key"], kwargs["index_type"]), ("chunk_id", VectorIndexType.DELTA_SYNC))
        spec = kwargs["delta_sync_index_spec"]
        self.assertEqual(spec.source_table, "workspace.default.a8_offline8_doc_chunks")
        self.assertEqual(spec.pipeline_type, PipelineType.TRIGGERED)
        self.assertEqual(spec.columns_to_sync, COLUMNS)
        self.assertEqual(spec.embedding_source_columns[0].name, "content")
        self.assertEqual(spec.embedding_source_columns[0].embedding_model_endpoint_name, "databricks-gte-large-en")

    def test_sdk_classes_accept_the_definition(self):
        spec = DeltaSyncVectorIndexSpecRequest(
            source_table="c.s.t", pipeline_type=PipelineType.TRIGGERED, columns_to_sync=COLUMNS,
            embedding_source_columns=[EmbeddingSourceColumn(name="content", embedding_model_endpoint_name="e")])
        body = spec.as_dict()
        self.assertEqual(body["pipeline_type"], "TRIGGERED")
        self.assertEqual(body["embedding_source_columns"][0]["name"], "content")

    def test_a_foreign_endpoint_with_the_same_name_is_refused(self):
        with self.assertRaisesRegex(AssertionError, "created by you"):
            self.run_lesson(endpoint=True, foreign_endpoint=True)
        self.assertFalse([c for c in self.fake.calls if c[0] in {"create_endpoint", "delete_endpoint"}])

    def test_deleting_a_foreign_endpoint_is_refused(self):
        with self.assertRaises(PermissionError):
            self.run_lesson(delete=True, foreign_endpoint=True)
        self.assertEqual([c for c in self.fake.calls if c[0].startswith("delete")], [])

    def test_exercise_solution_matches_independent_python_and_pyspark_style_answers(self):
        self.run_lesson()
        counts = {}
        for row in self.rows:
            if row[1].startswith("venue-"):
                counts[row[1]] = counts.get(row[1], 0) + 1
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["8c.1"]["solution"]).collect()]
        self.assertEqual(rows, sorted(counts.items()))
        self.course.test_with_solutions = False
        dataframe = SimpleNamespace(columns=["doc_name", "chunks"], collect=lambda: sorted(counts.items()))
        wrong = SimpleNamespace(columns=["doc_name", "chunks"], collect=lambda: [("venue-leeds.md", 99)])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.course.check("8c.1", dataframe))
            self.assertFalse(self.course.check("8c.1", wrong))
            self.assertFalse(self.course.check("8c.1", None))

    def test_notebook_standard_scope_and_navigation(self):
        tree = ast.parse(SOURCE)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for forbidden in ("A8.run", "A8.sql", "mlflow", "saveAsTable", "CREATE ", "DROP "):
            self.assertNotIn(forbidden, SOURCE)
        imported = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        self.assertFalse([m for m in imported if m.startswith("pyspark")])
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 4)
        text = SOURCE.replace("# MAGIC ", "")
        phrases = ("**Where this sits:**", "Free first", "Terms in this lesson", "live validated yet", "If it differs",
                   "bills for as long as it exists")
        for phrase in phrases:
            self.assertIn(phrase, text)
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/08b_rag.py"):
            self.assertIn("08c_vector_search", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 8c", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))
        self.assertIn("vector_search_for_cleanup", (ROOT / "notebooks/99_pause_and_cleanup.py").read_text() +
                      (ROOT / "lib/a8learn/lifecycle.py").read_text())


if __name__ == "__main__":
    unittest.main()
