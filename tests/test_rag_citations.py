"""SQL collect order must not change the document associated with a numbered citation."""
import ast
import contextlib
import io
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CitationTests(unittest.TestCase):
    def test_reordered_chat_rows_keep_their_own_sources_in_both_rag_lessons(self):
        for name in ("08b_rag.py", "08c_vector_search.py"):
            with self.subTest(notebook=name):
                tree = ast.parse((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
                # Run the actual display loop, without executing retrieval or model requests.
                block = next(n for n in tree.body if isinstance(n, ast.If) and any(
                    isinstance(child, ast.For) and "answers" in ast.unparse(child.iter) for child in n.body))
                nodes = [n for n in block.body if isinstance(n, ast.For) or (
                    isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "passages_by_question"
                                                     for t in n.targets))]
                namespace = {
                    "ask": [("Transfer?", [(1, {"doc_name": "booking-and-transfers.md"})]),
                            ("Bristol?", [(1, {"doc_name": "venue-bristol.md"})])],
                    "answers": [{"question": q, "reply": {"result": "Supported [1]", "errorMessage": None}}
                                for q in ("Bristol?", "Transfer?")],
                    "re": re, "REFUSAL": "I cannot answer",
                }
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    exec(compile(ast.Module(body=nodes, type_ignores=[]), name, "exec"), namespace)
                text = output.getvalue()
                self.assertIn("Q: Bristol?\nA: Supported [1]\nCited: ['venue-bristol.md']", text)
                self.assertIn("Q: Transfer?\nA: Supported [1]\nCited: ['booking-and-transfers.md']", text)


if __name__ == "__main__":
    unittest.main()
