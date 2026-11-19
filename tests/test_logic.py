import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from helpers import APP, ROOT
from logic import (
    SYSTEM_PROMPT, answer_live, build_messages, identifier, load_events,
    names, ownership_marker, require_owner, simulate_answer, with_availability,
)


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.rows = load_events()

    def test_independent_sql_facts_and_no_mutation(self):
        original = copy.deepcopy(self.rows)
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE events(event_id, event_name, city, capacity, booked)")
        db.executemany("INSERT INTO events VALUES (:event_id,:event_name,:city,:capacity,:booked)", self.rows)
        for city, limit, expected in [
            ("Leeds", 999, [("E101", 18), ("E104", 22)]),
            ("Manchester", 999, [("E102", 3), ("E106", 15)]),
            ("Manchester", 10, [("E102", 3)]),
            ("Bristol", 999, [("E105", 5)]),
        ]:
            actual = db.execute(
                "SELECT event_id, capacity-booked FROM events "
                "WHERE city=? AND capacity-booked < ? ORDER BY event_id", (city, limit),
            ).fetchall()
            self.assertEqual(actual, expected)
        self.assertEqual([r["remaining"] for r in with_availability(self.rows)], [18, 3, 35, 22, 5, 15])
        self.assertEqual(self.rows, original)

    def test_names_and_worst_case_lengths(self):
        self.assertEqual(names("training", "authorised", "learner07"),
                         ("training.authorised.a8learn_learner07_events", "a8learn-learner07-assistant"))
        names("a" * 48, "b" * 48, "c" * 16)
        for value in ("", "UPPER", "a-b", "a.b", "a`", "a;drop", "../x", "a b", "7abc", "é"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                identifier(value)
        for args in [("a"*49, "b", "c"), ("a", "b"*49, "c"), ("a", "b", "c"*17)]:
            with self.assertRaises(ValueError):
                names(*args)
        for catalog in ("system", "samples", "dbacademy"):
            with self.assertRaises(ValueError):
                names(catalog, "x", "learner07")

    def test_ownership_exact_not_prefix(self):
        require_owner(ownership_marker("learner07"), "learner07")
        for marker in (None, "", ownership_marker("other"), ownership_marker("learner07")+"extra"):
            with self.assertRaises(ValueError):
                require_owner(marker, "learner07")

    def test_fixture_validation(self):
        valid = (APP / "data/events.csv").read_text()
        for content in [
            "", valid.splitlines()[0]+"\n",
            valid.replace("60,42", "30,42"),
            valid.replace("60,42", "60,-1"),
            valid.replace("60,42", "sixty,42"),
            valid.replace("E102", "E101"),
            valid.replace("Analytics Breakfast", ""),
            valid.replace(",booked", ",reserved"),
            valid.replace("60,42", "60,42,extra"),
        ]:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "events.csv"
                path.write_text(content)
                with self.subTest(content=content[:50]), self.assertRaises((ValueError, TypeError)):
                    load_events(path)

    def test_messages_and_limits(self):
        messages = build_messages("  Which events are in Leeds?  ", self.rows)
        self.assertEqual(messages[0], {"role": "system", "content": SYSTEM_PROMPT})
        payload = json.loads(messages[1]["content"])
        self.assertEqual(len(payload["event_records"]), 6)
        self.assertEqual(payload["question"], "Which events are in Leeds?")
        self.assertEqual(payload["event_records"][0]["remaining"], 18)
        build_messages("x"*1000, self.rows)
        for question in ("", " ", "x"*1001, None):
            with self.assertRaises(ValueError):
                build_messages(question, self.rows)
        for text in ("untrusted", "event_id", "not an attendance forecast", "Do not invent", "cannot answer"):
            self.assertIn(text, SYSTEM_PROMPT)

    def test_simulation_is_explicit_and_scoped(self):
        answer = simulate_answer(" WHICH  events are in Leeds? ", self.rows)
        for text in ("Simulation, not AI", "E101", "18", "E104", "22"):
            self.assertIn(text, answer)
        self.assertIn("only supports", simulate_answer("What is the cancellation policy?", self.rows))
        changed = copy.deepcopy(self.rows)
        changed[0]["booked"] += 1
        self.assertIn("17", simulate_answer("Which events are in Leeds?", changed))

    def test_live_single_injected_call(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" E102: 3 places. "))]
        )
        self.assertEqual(answer_live(client, "approved-model", "Manchester under ten?", self.rows),
                         "E102: 3 places.")
        call = client.chat.completions.create
        call.assert_called_once()
        self.assertEqual(call.call_args.kwargs["model"], "approved-model")
        self.assertEqual(call.call_args.kwargs["max_tokens"], 1024)
        self.assertEqual(len(json.loads(call.call_args.kwargs["messages"][1]["content"])["event_records"]), 6)

    def test_live_errors_and_validation_never_retry(self):
        for response in (
            SimpleNamespace(choices=[]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" "))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))]),
        ):
            client = Mock()
            client.chat.completions.create.return_value = response
            with self.assertRaises(ValueError):
                answer_live(client, "approved", "Hello", self.rows)
            client.chat.completions.create.assert_called_once()
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError("injected")
        with self.assertRaises(RuntimeError):
            answer_live(client, "approved", "Hello", self.rows)
        client.chat.completions.create.assert_called_once()
        client.reset_mock()
        with self.assertRaises(ValueError):
            answer_live(client, "", "Hello", self.rows)
        client.chat.completions.create.assert_not_called()

    def test_playground_example_matches_code_contract(self):
        text = (ROOT / "docs/lessons/02-model.md").read_text(encoding="utf-8")
        system = text.split("```text\n")[1].split("```")[0].strip()
        payload = json.loads(text.split("```json\n")[1].split("```")[0])
        self.assertEqual(system, SYSTEM_PROMPT)
        self.assertEqual(payload, json.loads(build_messages("Which events are in Leeds?", self.rows)[1]["content"]))
