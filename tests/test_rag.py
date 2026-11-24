"""Offline checks for Module 8b. No model is ever called: ai_query is replaced by deterministic stand-ins.

The notebook's Python cells run against the shipped documents, a temporary folder standing in for the volume and
SQLite for the chunk table. Whether embedding or chat endpoints exist, their quota, and the quality of real answers
are not tested here.
"""
import ast
import contextlib
import io
import re
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import PropertyMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
from a8learn import OBJECTS, Config, Course
from a8learn.exercises import EXERCISES
from test_descriptive import OfflineSpark

NOTEBOOK = ROOT / "notebooks/08b_rag.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
DOCS = sorted((ROOT / "data/docs").glob("*.md"))


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows


class SourceView:
    """Stands in for the DataFrame of chunk values: remembers the rows and the view name."""

    def __init__(self, spark, columns, rows):
        self.spark, self.columns, self.rows = spark, columns, rows

    def createOrReplaceTempView(self, name):
        self.spark.views[name] = (self.columns, self.rows)


class Catalog:
    def __init__(self, spark):
        self.spark = spark

    def dropTempView(self, name):
        self.spark.views.pop(name, None)


def hashed_vector(text, dims=64):
    vector = np.zeros(dims)
    for word in re.findall(r"[a-z']+", text.lower()):
        vector[zlib.crc32(word.encode()) % dims] += 1
    return list(vector)


class StandInSpark(OfflineSpark):
    """Plain SQL goes to SQLite. Chunk-table DDL and ai_query are recorded and answered without any model."""

    def __init__(self, course):
        super().__init__(course)
        self.views, self.embed_calls, self.chat_calls = {}, [], []
        self.catalog = Catalog(self)

    def sql(self, statement, args=None):
        if "ai_query" in statement and "AS embedding" in statement:
            self.statements.append(statement)
            self.embed_calls.append((statement, args))
            texts = [v for _, v in sorted(args.items(), key=lambda kv: int(kv[0][1:]))]
            return Rows([{"text": t, "embedding": hashed_vector(t)} for t in texts])
        if "ai_query" in statement:
            self.statements.append(statement)
            self.chat_calls.append((statement, args))
            count = len(args) // 2
            return Rows([{"question": args[f"q{i}"],
                          "result": {"response": f"Stand-in answer citing [1]. {args[f'q{i}'][:10]}",
                                     "errorMessage": None}} for i in range(count)])
        if statement.startswith("SELECT * FROM VALUES"):
            self.statements.append(statement)
            columns = re.search(r"AS v\(([^)]*)\)", statement).group(1).split(", ")
            count = len(args) // len(columns)
            rows = [tuple(args[f"{c}{i}"] for c in columns) for i in range(count)]
            return SourceView(self, columns, rows)
        match = re.match(r"CREATE OR REPLACE TABLE (\S+)", statement)
        if match:
            self.statements.append(statement)
            columns, rows = self.views["a8_source_doc_chunks"]
            self.db.execute("DROP TABLE IF EXISTS doc_chunks")
            self.db.execute(f"CREATE TABLE doc_chunks ({', '.join(c + ' TEXT' for c in columns)})")
            self.db.executemany(f"INSERT INTO doc_chunks VALUES ({', '.join('?' for _ in columns)})", rows)
            return Rows([])
        return super().sql(statement)


class RagTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline8", "synthetic@example.com", "https://example.com"),
                             answers="solutions")
        self.spark = StandInSpark(self.course)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.volume = tempfile.TemporaryDirectory()
        self.addCleanup(self.volume.cleanup)

    def run_lesson(self, embed=False, ask=False):
        class Dbutils:
            pass

        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        approvals = {"embed_chunks": embed, "ask_model": ask}
        with patch.object(Course, "volume_path", new_callable=PropertyMock, return_value=self.volume.name), \
             patch.object(self.course, "require"), patch.object(self.course, "guard"), \
             patch.object(self.course, "gate", lambda name, label: approvals[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    def expected_sections(self):
        return {p.name: re.findall(r"^## (.+)$", p.read_text(encoding="utf-8"), re.M) for p in DOCS}

    def test_default_run_calls_no_model_and_writes_only_the_chunk_table(self):
        namespace = self.run_lesson()
        self.assertEqual(self.spark.embed_calls, [])
        self.assertEqual(self.spark.chat_calls, [])
        self.assertIsNone(namespace["embeddings"])
        self.assertIsNone(namespace["answers"])
        writes = [q for q in self.spark.statements
                  if q.lstrip().upper().startswith(("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(len(writes), 1)
        self.assertIn("'delta.enableChangeDataFeed' = 'true'", writes[0])
        self.assertIn("'a8learn.course' = 'a8-databricks-learning'", writes[0])
        self.assertEqual(self.spark.views, {})  # the source view is dropped

    def test_documents_are_copied_and_chunked_by_section(self):
        namespace = self.run_lesson()
        self.assertEqual(sorted(p.name for p in (Path(self.volume.name) / "docs").glob("*.md")),
                         [p.name for p in DOCS])
        sections = self.expected_sections()
        self.assertEqual(len(namespace["chunks"]), sum(len(v) for v in sections.values()))
        for name, headings in sections.items():
            self.assertEqual([c["section"] for c in namespace["chunks"] if c["doc_name"] == name], headings)
        self.assertLessEqual(max(len(c["content"]) for c in namespace["chunks"]), 800)
        self.assertEqual(self.spark.table("doc_chunks").count(), len(namespace["chunks"]))

    def test_chunk_text_travels_as_parameters_not_sql(self):
        namespace = self.run_lesson()
        for statement in self.spark.statements:
            for chunk in namespace["chunks"][:5]:
                self.assertNotIn(chunk["content"], statement)

    def test_evaluation_questions_point_at_real_documents(self):
        namespace = self.run_lesson()
        names = {p.name for p in DOCS}
        self.assertEqual(len(namespace["EVAL"]), 8)
        for _, doc in namespace["EVAL"]:
            self.assertIn(doc, names)
        hit_rate, word_search = namespace["hit_rate"], namespace["word_search"]
        # The questions are chosen so word overlap misses some at k=1 and nearly all at k=3, as the lesson says.
        self.assertEqual((hit_rate(word_search, 1), hit_rate(word_search, 3)), (0.5, 0.875))

    def test_approved_embedding_sends_every_text_once(self):
        namespace = self.run_lesson(embed=True)
        self.assertEqual(len(self.spark.embed_calls), 1)
        statement, args = self.spark.embed_calls[0]
        self.assertEqual(len(args), len(namespace["texts"]))
        self.assertEqual(len(namespace["texts"]), len(namespace["chunks"]) + 9)
        self.assertIn("'databricks-gte-large-en'", statement)
        self.assertEqual(self.spark.chat_calls, [])
        self.assertIs(namespace["search"], namespace["embedding_search"])
        top = namespace["embedding_search"]("Can I give my ticket to a colleague?", 3)
        self.assertEqual(len(top), 3)
        self.assertGreaterEqual(top[0][0], top[1][0])

    def test_approved_chat_sends_two_grounded_prompts(self):
        namespace = self.run_lesson(ask=True)
        self.assertEqual(len(self.spark.chat_calls), 1)
        statement, args = self.spark.chat_calls[0]
        self.assertEqual(len(args), 4)
        self.assertIn("failOnError => false", statement)
        self.assertIn("'databricks-meta-llama-3-3-70b-instruct'", statement)
        for prompt in namespace["prompts"]:
            self.assertIn(namespace["REFUSAL"], prompt)
            self.assertNotIn(prompt, statement)
            self.assertEqual(prompt.count("\n["), 3)
        self.assertIn("Cited:", self.output)
        self.assertEqual(self.spark.embed_calls, [])

    def test_exercise_solutions_match_independent_python(self):
        namespace = self.run_lesson()
        counts = {name: len(headings) for name, headings in self.expected_sections().items()}
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["8b.1"]["solution"]).collect()]
        self.assertEqual(rows, sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        refunds = sorted((c["doc_name"], c["section"]) for c in namespace["chunks"]
                         if "refund" in c["content"].lower())
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["8b.2"]["solution"]).collect()]
        self.assertEqual(rows, refunds)
        self.assertTrue(rows)

    def test_blank_and_naive_exercise_answers_fail(self):
        self.run_lesson()
        naive = ("SELECT doc_name, section FROM IDENTIFIER(a8_doc_chunks) WHERE lower(content) LIKE '%refunded%' "
                 "ORDER BY doc_name, section")
        self.course.test_with_solutions = False
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("8b.2", ""))
            self.assertFalse(self.course.check("8b.2", naive))  # 'refunded' finds one chunk, not every mention

    def test_notebook_standard_scope_and_cleanup(self):
        tree = ast.parse(SOURCE)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for forbidden in ("A8.run", "A8.sql", "mlflow", "serving_endpoints", "vector_search", "VectorSearch"):
            self.assertNotIn(forbidden, SOURCE)
        text = SOURCE.replace("# MAGIC ", "")
        phrases = ("**Where this sits:**", "Free first", "Terms in this lesson", "live validated yet", "If it differs")
        for phrase in phrases:
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 2)
        self.assertEqual(OBJECTS["doc_chunks"], ("table", "08b_rag"))
        self.assertIn('"doc_chunks"', (ROOT / "lib/a8learn/lifecycle.py").read_text(encoding="utf-8"))

    def test_navigation_mentions_module_8b(self):
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/08a_embeddings.py"):
            self.assertIn("08b_rag", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 8b", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
