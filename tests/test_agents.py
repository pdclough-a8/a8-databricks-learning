"""Offline checks for Module 9. No model is ever called: ai_query is replaced by a scripted stand-in.

The notebook's Python cells run against the shipped events and bookings in SQLite and a chunk table built from the
shipped documents. Whether a real model picks the right tool, and the quality of its answers, are not tested here.
"""
import ast
import contextlib
import csv
import io
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
from a8learn import OBJECTS, Config, Course
from a8learn.exercises import EXERCISES, REFLECTIONS
from test_descriptive import OfflineSpark, Result

NOTEBOOK = ROOT / "notebooks/09_agents.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
WRITES = ("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE", "MERGE")


def rows_of(name):
    with (ROOT / "data/raw" / name).open(encoding="utf-8", newline="") as handle:
        return [{k: (int(v) if k in {"capacity", "tickets"} else v) for k, v in row.items()}
                for row in csv.DictReader(handle)]


class Replies:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows


class StandInSpark(OfflineSpark):
    """SQL goes to SQLite with named parameters. ai_query is answered by a function of the prompt."""

    def __init__(self, course, reply):
        super().__init__(course)
        self.reply, self.chat_calls = reply, []
        self.load("events", rows_of("events.csv"))
        self.load("bookings", rows_of("bookings.csv"))
        self.db.execute("""CREATE VIEW event_availability AS SELECT e.event_id, e.event_name, e.city, e.event_date,
e.status, e.capacity, coalesce(sum(b.tickets), 0) AS booked, e.capacity - coalesce(sum(b.tickets), 0) AS available
FROM events e LEFT JOIN bookings b ON e.event_id = b.event_id AND b.status = 'confirmed'
GROUP BY e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity""")
        self.db.execute("CREATE TABLE doc_chunks (doc_name TEXT, section TEXT, content TEXT)")
        for path in sorted((ROOT / "data/docs").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
            parts = re.split(r"^## (.+)$", text, flags=re.M)
            for heading, body in zip(parts[1::2], parts[2::2], strict=True):
                self.db.execute("INSERT INTO doc_chunks VALUES (?, ?, ?)",
                                (path.name, heading.strip(), f"{title} - {heading.strip()}: {' '.join(body.split())}"))

    def sql(self, statement, args=None):
        self.statements.append(statement)
        if "ai_query" in statement:
            self.chat_calls.append(args["prompt"])
            return Replies([{"reply": self.reply(args["prompt"])}])
        for key in OBJECTS:
            statement = statement.replace(f"IDENTIFIER(a8_{key})", key).replace(self.course.t(key), key)
        return Result(self.db.execute(statement, args or {}))


def good_reply(prompt):
    """A well-behaved model: check seats for a named event, search documents otherwise, then answer from the step."""
    task = re.search(r"Task: (.+)\n", prompt).group(1)
    if "Steps so far: none" not in prompt:
        step = re.search(r"Step 1: (\w+)\(.*? -> (.+)", prompt).group(2)
        return {"result": json.dumps({"final": f"From the tool: {step[:200]}"}), "errorMessage": None}
    if "weather" in task.lower():
        return {"result": json.dumps({"final": "I can't find that in the A8 Events documents."}), "errorMessage": None}
    if "Breakfast" in task or "Pipelines" in task:
        name = "Analytics Breakfast" if "Breakfast" in task else "Pipelines in Practice"
        return {"result": json.dumps({"tool": "check_availability", "args": {"event_name": name}}),
                "errorMessage": None}
    return {"result": f'```json\n{json.dumps({"tool": "search_docs", "args": {"query": task}})}\n```',
            "errorMessage": None}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline9", "synthetic@example.com", "https://example.com"),
                             answers="solutions")

    def run_lesson(self, approve=False, reply=good_reply):
        self.spark = StandInSpark(self.course, reply)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark

        class Dbutils:
            pass

        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        with patch.object(self.course, "require"), patch.object(self.course, "guard"), \
             patch.object(self.course, "gate", lambda name, label: approve and name == "ask_agent"), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    def test_default_run_calls_no_model_and_writes_nothing(self):
        namespace = self.run_lesson()
        self.assertEqual(self.spark.chat_calls, [])
        self.assertIsNone(namespace["model_results"])
        self.assertEqual([q for q in self.spark.statements if q.lstrip().upper().startswith(WRITES)], [])

    def test_rule_agent_scores_as_the_lesson_describes(self):
        namespace = self.run_lesson()
        results = namespace["rules_results"]
        self.assertEqual([r[2] for r in results], [True] * 5)  # the rules pick the right tool on all five
        # 'take over my seat' ranks the wrong section first, so only that answer is ungrounded
        self.assertEqual([r[3] for r in results], [True, True, False, True, True])
        self.assertIn("Rules: tool choice 5/5, grounded 4/5", self.output)

    def test_seat_facts_come_from_the_view_not_the_agent(self):
        namespace = self.run_lesson()
        events = {(e["event_name"], e["city"]): e for e in rows_of("events.csv") if e["status"] == "scheduled"}
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        e = events[("Pipelines in Practice", "Bristol")]
        self.assertEqual(namespace["TASKS"][0]["fact"], str(e["capacity"] - booked.get(e["event_id"], 0)))

    def test_guardrails(self):
        namespace = self.run_lesson()
        run_tool = namespace["run_tool"]
        self.assertIn("Unknown tool", run_tool("drop_table", {"query": "x"})["error"])
        self.assertIn("error", run_tool("search_docs", {"query": "a"}))
        self.assertIn("error", run_tool("search_docs", {"query": "x" * 81}))
        self.assertIn("error", run_tool("search_docs", {"query": "refund", "k": "9"}))
        self.assertIn("error", run_tool("search_docs", "refund"))
        self.assertIn("result", run_tool("search_docs", {"query": "refund"}))

    def test_tool_input_travels_as_a_parameter(self):
        namespace = self.run_lesson()
        hostile = "x' OR '1'='1"
        self.assertEqual(namespace["check_availability"](hostile), [])
        self.assertTrue(all(hostile not in q for q in self.spark.statements))

    def test_failing_tool_becomes_an_error_message(self):
        namespace = self.run_lesson()
        namespace["TOOLS"]["search_docs"]["function"] = lambda q: 1 / 0
        outcome = namespace["run_tool"]("search_docs", {"query": "refund"})
        self.assertEqual(outcome, {"error": "search_docs failed: ZeroDivisionError"})

    def test_loop_step_cap_and_invalid_decisions(self):
        namespace = self.run_lesson()
        run_agent = namespace["run_agent"]
        endless = run_agent("t", lambda task, trace: {"tool": "search_docs", "args": {"query": "refund"}})
        self.assertEqual((endless["status"], len(endless["trace"])), ("stopped: step cap reached", 4))
        self.assertEqual(run_agent("t", lambda task, trace: {"oops": 1})["status"], "stopped: invalid decision")
        unknown = run_agent("t", lambda task, trace: {"tool": "x", "args": {}} if not trace else {"final": "done"})
        self.assertEqual(unknown["status"], "answered")
        self.assertIn("Unknown tool", unknown["trace"][0]["error"])

    def test_parse_decision(self):
        parse = self.run_lesson()["parse_decision"]
        self.assertEqual(parse('Sure! {"final": "ok"}'), {"final": "ok"})
        self.assertEqual(parse('{"tool": "search_docs", "args": {"query": "q"}}')["tool"], "search_docs")
        for bad in ("", None, "no json", '{"tool": "search_docs"}', '{"tool": ', "[1, 2]", '{"a": 1}'):
            self.assertIn("error", parse(bad), bad)

    def test_approved_model_agent_is_scored_and_stays_inside_the_budget(self):
        namespace = self.run_lesson(approve=True)
        self.assertLessEqual(len(self.spark.chat_calls), 12)
        self.assertEqual(namespace["model_calls"]["used"], len(self.spark.chat_calls))
        results = namespace["model_results"]
        self.assertEqual([r[1]["status"] for r in results], ["answered"] * 5)
        self.assertEqual([r[2] for r in results], [True, True, True, True, True])
        self.assertEqual([r[3] for r in results][:2] + [results[4][3]], [True, True, True])  # seats and refusal
        self.assertIn("Model: tool choice 5/5", self.output)
        self.assertTrue(all(prompt.count("Task:") == 1 for prompt in self.spark.chat_calls))

    def test_budget_stops_a_model_that_never_finishes(self):
        def endless(prompt):
            return {"result": '{"tool": "search_docs", "args": {"query": "refund"}}', "errorMessage": None}

        namespace = self.run_lesson(approve=True, reply=endless)
        self.assertEqual(len(self.spark.chat_calls), 12)
        statuses = [r[1]["status"] for r in namespace["model_results"]]
        self.assertIn("stopped: the chat request budget is used up", statuses)

    def test_chat_errors_and_bad_replies_stop_the_task_without_a_crash(self):
        def failing(prompt):
            return {"result": None, "errorMessage": "endpoint not found"}

        namespace = self.run_lesson(approve=True, reply=failing)
        self.assertTrue(all(r[1]["status"] == "stopped: the chat request failed" for r in namespace["model_results"]))
        self.assertEqual(namespace["model_calls"]["errors"][0], "endpoint not found")

        def chatty(prompt):
            return {"result": "I would check the documents.", "errorMessage": None}

        namespace = self.run_lesson(approve=True, reply=chatty)
        self.assertTrue(all("not valid JSON" in r[1]["status"] for r in namespace["model_results"]))

    def test_exercise_solutions_match_independent_python(self):
        self.run_lesson()
        scheduled = [e for e in rows_of("events.csv") if e["status"] == "scheduled"]
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        left = [(e["event_name"], e["city"], e["capacity"] - booked.get(e["event_id"], 0)) for e in scheduled]
        expected = sorted((r for r in left if r[1] in {"London", "Manchester"}), key=lambda r: (-r[2], r[0], r[1]))
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["9.1"]["solution"]).collect()]
        self.assertEqual(rows, expected)
        self.assertTrue(rows)
        open_by_city = {}
        for _, city, seats in left:
            if seats > 0:
                open_by_city[city] = open_by_city.get(city, 0) + 1
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["9.2"]["solution"]).collect()]
        self.assertEqual(rows, sorted(open_by_city.items(), key=lambda kv: (-kv[1], kv[0])))

    def test_blank_and_naive_exercise_answers_fail(self):
        self.run_lesson()
        self.course.test_with_solutions = False
        naive = ("SELECT city, count(*) AS open_events FROM IDENTIFIER(a8_event_availability) "
                 "GROUP BY city ORDER BY open_events DESC, city")  # counts every event, not only open scheduled ones
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("9.2", ""))
            self.assertFalse(self.course.check("9.2", naive))

    def test_notebook_standard_scope_and_navigation(self):
        tree = ast.parse(SOURCE)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for forbidden in ("A8.run", "A8.sql", "mlflow", "serving_endpoints", "vector_search", "VectorSearch"):
            self.assertNotIn(forbidden, SOURCE)
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "If it differs", "Cost boundary"):
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 1)
        self.assertEqual({"9.a", "9.b"} - set(REFLECTIONS), set())
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/08c_vector_search.py"):
            self.assertIn("09_agents", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 9", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
