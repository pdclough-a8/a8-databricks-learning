"""Offline checks for Module 15. No MLflow, workspace, model or endpoint is contacted.

MLflow's registry and the serving REST API are replaced by stand-ins that keep real state (versions, tags, the alias,
the endpoint's served entities), and evaluation really runs the agent and the scorers, so the gate decisions and the
order of writes are the notebook's own. These tests do not show how MLflow 3.6 or Databricks behaves, and the canary's
request fields are unconfirmed: see docs/validation.md for live status.
"""
import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "lib"))
sys.path.insert(0, str(ROOT_DIR / "tests"))
from a8learn import Config, Course, agent_core, release
from a8learn import evaluation as ev
from a8learn.exercises import EXERCISES, REFLECTIONS
from test_agents import ROOT, StandInSpark, rows_of
from test_deploy import snapshot_from
from test_evaluation import FakeMlflow, FakeWorkspace

NOTEBOOK = ROOT / "notebooks/15_release_and_rollback.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")


class RegistryMlflow(FakeMlflow):
    """FakeMlflow plus a Unity Catalog registry: versions with snapshots and tags, and one movable alias."""

    def __init__(self, champion_snapshot=None):
        super().__init__()
        self.versions, self.alias, self.alias_history, self.logged = {}, {}, [], None
        if champion_snapshot is not None:
            self.versions[1] = {"snapshot": champion_snapshot, "tags": {}}
            self.alias["Champion"] = 1
        outer = self

        class MlflowClient:
            def set_tag(self, run_id, key, value):
                outer.calls.append(("set_tag", run_id, key, value))

            def get_model_version_by_alias(self, name, alias):
                return self.get_model_version(name, outer.alias[alias])  # KeyError when there is none

            def get_model_version(self, name, version):
                return SimpleNamespace(version=str(version), tags=outer.versions[int(version)]["tags"])

            def set_registered_model_alias(self, name, alias, version):
                outer.alias[alias] = int(version)
                outer.alias_history.append(int(version))

            def set_model_version_tag(self, name, version, key, value):
                outer.versions[int(version)]["tags"][key] = value

        self.MlflowClient = MlflowClient
        self.pyfunc = SimpleNamespace(log_model=self.log_model, load_model=self.load_model)

    def set_registry_uri(self, uri):
        self.calls.append(("set_registry_uri", uri))

    @contextlib.contextmanager
    def start_run(self, run_name=None):
        self.calls.append(("start_run", run_name))
        yield SimpleNamespace(info=SimpleNamespace(run_id="r"))

    def set_tags(self, tags):
        self.calls.append(("set_tags", tags))

    def log_model(self, name, python_model, code_paths, artifacts, input_example):
        self.logged = json.loads(Path(artifacts["snapshot"]).read_text(encoding="utf-8"))
        return SimpleNamespace(model_uri="runs:/r/agent")

    def register_model(self, uri, name):
        number = max(self.versions, default=0) + 1
        self.versions[number] = {"snapshot": self.logged, "tags": {}}
        self.calls.append(("register_model", number))
        return SimpleNamespace(version=str(number))  # MLflow returns versions as text

    def load_model(self, uri):
        version = self.alias["Champion"] if uri.endswith("@Champion") else int(uri.rsplit("/", 1)[1])
        snapshot = self.versions[version]["snapshot"]

        def predict(frame):
            results = [agent_core.answer(snapshot, q) for q in frame["question"]]
            return pd.DataFrame({"answer": [r["answer"] for r in results], "status": [r["status"] for r in results],
                                 "steps": [",".join(r["steps"]) for r in results]})
        return SimpleNamespace(predict=predict)


class EndpointWorkspace(FakeWorkspace):
    """FakeWorkspace whose serving REST API keeps the endpoint's served entities and traffic routes."""

    def __init__(self, user, model, fail_on_request=None):
        super().__init__(user)
        self.model, self.fail_on_request, self.puts, self.posts = model, fail_on_request, [], 0
        self.config = {"served_entities": [{"name": "agent-1", "entity_name": model, "entity_version": "1"}],
                       "traffic_config": {"routes": [{"served_model_name": "agent-1", "traffic_percentage": 100}]}}

    def do(self, method, path, body=None):
        if method == "GET":
            return {"config": self.config, "state": {"config_update": "NOT_UPDATING", "ready": "READY"}}
        if method == "PUT":
            self.puts.append(body)
            self.config = {"served_entities": body["served_entities"], "traffic_config": body["traffic_config"]}
            return {}
        self.posts += 1
        if self.fail_on_request and self.posts == self.fail_on_request:
            raise RuntimeError("request failed")
        return super().do(method, path, body)


class RuleTests(unittest.TestCase):
    def verdict(self, passed):
        return {"passed": passed, "reasons": [] if passed else ["grounded/mean fell from 0.80 to 0.40"]}

    def test_alias_moves_only_when_the_gate_passes_and_the_record_is_written_either_way(self):
        client = Mock()
        self.assertTrue(release.record_and_release(client, "m", 2, self.verdict(True), "run9", 1))
        client.set_registered_model_alias.assert_called_once_with("m", "Champion", 2)
        client.set_model_version_tag.assert_any_call("m", 2, "evaluation_run_id", "run9")
        client.set_model_version_tag.assert_any_call("m", 2, "replaces", "1")
        client = Mock()
        self.assertFalse(release.record_and_release(client, "m", 3, self.verdict(False), "run10", 2))
        client.set_registered_model_alias.assert_not_called()
        written = {c.args[2]: c.args[3] for c in client.set_model_version_tag.call_args_list}
        self.assertEqual(written["gate"], "blocked")
        self.assertIn("grounded/mean fell", written["gate_reasons"])
        self.assertNotIn("replaces", written)

    def test_roll_back_uses_the_replaces_tag_and_refuses_without_one(self):
        client = Mock()
        client.get_model_version_by_alias.return_value = SimpleNamespace(version="2", tags={"replaces": "1"})
        self.assertEqual(release.roll_back(client, "m"), "1")
        client.set_registered_model_alias.assert_called_once_with("m", "Champion", "1")
        client.set_model_version_tag.assert_called_once_with("m", "2", "withdrawn", "yes")
        client.get_model_version_by_alias.return_value = SimpleNamespace(version="1", tags={})
        with self.assertRaises(ValueError):
            release.roll_back(client, "m")

    def test_canary_bodies_split_and_restore(self):
        split, restore = release.canary_bodies("m", "agent-1", "1", 4, percent=10)
        self.assertEqual(release.routes({"config": split}), {"agent-1": 90, "candidate": 10})
        self.assertEqual([e["entity_version"] for e in split["served_entities"]], ["1", "4"])
        self.assertEqual(release.routes({"config": restore}), {"agent-1": 100})
        self.assertEqual(len(restore["served_entities"]), 1)
        for bad in (0, 100, -5):
            with self.assertRaises(ValueError):
                release.canary_bodies("m", "agent-1", "1", 4, percent=bad)

    def test_predict_adapter_returns_what_the_scorers_read(self):
        model = SimpleNamespace(predict=lambda frame: pd.DataFrame(
            {"answer": ["x"], "status": ["answered"], "steps": ["search_docs"]}))
        out = release.predict_with_model(model)("q")
        self.assertEqual(out, {"answer": "x", "status": "answered", "steps": "search_docs"})
        self.assertTrue(ev.right_tool(out, ev.make_expectations("search_docs", "")))


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline15", "synthetic@example.com",
                                    "https://example.com"), answers="solutions")

    def run_lesson(self, champion_stale=False, no_champion=False, endpoint=None, fail_on_request=None, **approvals):
        self.spark = StandInSpark(self.course, lambda prompt: None)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        truth = {**snapshot_from(self.spark), "taken_on": "now"}
        self.truth = truth
        champion_snapshot = None if no_champion else (ev.stale_snapshot(truth) if champion_stale else truth)
        self.mlflow = RegistryMlflow(champion_snapshot)
        self.w = EndpointWorkspace(self.course.cfg.user, self.course.agent_model_name, fail_on_request)
        self.w.snapshot = truth
        if endpoint:
            self.w.endpoints[self.course.agent_endpoint_name] = SimpleNamespace(
                id="x", creator=self.course.cfg.user,
                tags=[SimpleNamespace(key=k, value=v) for k, v in self.course.course_tags.items()])
        if endpoint == "other-model":
            self.w.config["served_entities"][0]["entity_name"] = "someone.else.model"

        class Dbutils:
            library = SimpleNamespace(restartPython=lambda: None)

        gates = {"log_candidates": False, "release_candidate": False, "roll_back": False,
                 "canary_endpoint": False, **approvals}
        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        self.claim, self.claim_model = Mock(), Mock()
        with patch.dict(sys.modules, {"mlflow": self.mlflow, "mlflow.genai": self.mlflow.genai,
                                      "mlflow.genai.scorers": self.mlflow.scorers}), \
             patch.object(sys, "path", list(sys.path)), \
             patch("databricks.sdk.WorkspaceClient", return_value=self.w), \
             patch.object(self.course, "require"), patch.object(self.course, "links"), \
             patch.object(self.course, "claim_experiment", self.claim), \
             patch.object(self.course, "claim_model", self.claim_model), \
             patch.object(self.course, "mark_experiment"), \
             patch.object(self.course, "gate", lambda name, label: gates[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            try:
                exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
            finally:
                self.output = out.getvalue()
        return namespace

    def evaluations(self):
        return [c for c in self.mlflow.calls if c[0] == "evaluate"]

    def test_default_run_writes_nothing(self):
        self.run_lesson()
        self.assertEqual(self.mlflow.calls, [("set_registry_uri", "databricks-uc")])
        self.assertEqual((list(self.mlflow.versions), self.mlflow.alias_history), ([1], []))
        self.assertEqual(self.w.puts, [])
        self.claim.assert_not_called()
        self.assertIn("Champion: 1", self.output)
        self.assertIn("Skipped: no baseline.", self.output)

    def test_without_a_champion_it_explains_and_writes_nothing(self):
        self.run_lesson(no_champion=True, log_candidates=True, release_candidate=True, roll_back=True)
        self.assertIn("There is no Champion to compare with", self.output)
        self.assertEqual(self.evaluations(), [])
        self.assertEqual(self.mlflow.versions, {})

    def test_candidates_are_logged_and_evaluated_but_the_alias_stays_until_released(self):
        namespace = self.run_lesson(log_candidates=True)
        self.assertEqual(len(self.evaluations()), 3)
        self.assertEqual((sorted(self.mlflow.versions), self.mlflow.alias_history), ([1, 2, 3], []))
        self.assertEqual(self.mlflow.alias, {"Champion": 1})
        self.assertEqual(namespace["baseline"]["grounded/mean"], 0.8)
        self.assertTrue(namespace["good_verdict"]["passed"])
        self.assertEqual(self.claim.call_args.args[1], self.course.evaluation_experiment_path)
        self.claim_model.assert_called_once()
        self.assertIn("Skipped: the alias was not moved.", self.output)

    def test_release_moves_the_alias_only_to_the_version_that_passes_and_records_the_decision(self):
        namespace = self.run_lesson(log_candidates=True, release_candidate=True)
        self.assertEqual(self.mlflow.alias_history, [2])  # the stale version 3 never held the alias
        self.assertEqual(self.mlflow.alias["Champion"], 2)
        good, bad = self.mlflow.versions[2]["tags"], self.mlflow.versions[3]["tags"]
        self.assertEqual((good["gate"], good["replaces"], good["compared_with_version"]), ("passed", "1", "1"))
        self.assertEqual((bad["gate"], bad["compared_with_version"]), ("blocked", "2"))
        self.assertIn("grounded/mean", bad["gate_reasons"])
        self.assertNotIn("replaces", bad)
        self.assertNotEqual(good["evaluation_run_id"], bad["evaluation_run_id"])
        self.assertFalse(namespace["bad_verdict"]["passed"])
        self.assertIn("blocked", self.output)

    def test_rollback_restores_the_champion_and_its_answers(self):
        self.run_lesson(log_candidates=True, release_candidate=True, roll_back=True)
        self.assertEqual(self.mlflow.alias_history, [2, 1])
        self.assertEqual(self.mlflow.alias["Champion"], 1)
        self.assertEqual(self.mlflow.versions[2]["tags"]["withdrawn"], "yes")
        self.assertIn("Champion is version 1 again", self.output)

    def test_rollback_without_a_release_does_nothing(self):
        self.run_lesson(log_candidates=True, roll_back=True)
        self.assertEqual(self.mlflow.alias_history, [])
        self.assertIn("nothing was released, so there is nothing to roll back", self.output)

    def test_a_stale_champion_still_blocks_a_stale_candidate_because_of_the_release_order(self):
        namespace = self.run_lesson(champion_stale=True, log_candidates=True, release_candidate=True, roll_back=False)
        # Against a Champion as stale as itself the stale candidate would tie and pass: a gate only compares.
        self.assertTrue(ev.release_gate(namespace["baseline"], namespace["bad_means"])["passed"])
        self.assertTrue(namespace["good_verdict"]["passed"])  # the fresh candidate beats the stale Champion
        self.assertFalse(namespace["bad_verdict"]["passed"])  # and the stale one is judged against the fresh Champion
        self.assertEqual(self.mlflow.alias_history, [2])

    # ---------- canary ----------
    def test_canary_splits_then_restores_and_checks_the_routes(self):
        self.run_lesson(endpoint=True, log_candidates=True, canary_endpoint=True)
        split, restore = self.w.puts
        self.assertEqual(release.routes({"config": split}), {"agent-1": 90, "candidate": 10})
        self.assertEqual(release.routes({"config": restore}), {"agent-1": 100})
        self.assertEqual(self.w.posts, 20)
        self.assertIn("after restore: {'agent-1': 100}", self.output)
        self.assertEqual(self.mlflow.alias_history, [])  # a canary never moves the alias

    def test_canary_restores_the_endpoint_even_when_a_request_fails(self):
        with self.assertRaises(RuntimeError):
            self.run_lesson(endpoint=True, log_candidates=True, canary_endpoint=True, fail_on_request=5)
        self.assertEqual(len(self.w.puts), 2)
        self.assertEqual(release.routes({"config": self.w.config}), {"agent-1": 100})

    def test_canary_without_an_endpoint_or_candidates_or_the_right_model_changes_nothing(self):
        self.run_lesson(log_candidates=True, canary_endpoint=True)
        self.assertEqual(self.w.puts, [])
        self.assertIn("There is no agent endpoint of yours to split", self.output)
        self.run_lesson(endpoint=True, canary_endpoint=True)
        self.assertEqual(self.w.puts, [])
        self.assertIn("log the candidates first", self.output)
        self.run_lesson(endpoint="other-model", log_candidates=True, canary_endpoint=True)
        self.assertEqual(self.w.puts, [])
        self.assertIn("does not serve a single version of your agent model", self.output)

    # ---------- course plumbing ----------
    def test_exercise_solution_matches_independent_python_and_naive_answers_fail(self):
        spark = StandInSpark(self.course, lambda prompt: None)
        self.addCleanup(spark.db.close)
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        expected = sorted((e["event_name"], e["city"], e["capacity"] - booked.get(e["event_id"], 0),
                           e["capacity"] - booked.get(e["event_id"], 0) + 7)
                          for e in rows_of("events.csv")
                          if e["status"] == "scheduled" and e["event_name"] in {"Pipelines in Practice",
                                                                                 "Analytics Breakfast"})
        self.assertGreaterEqual(len(expected), 2)
        self.assertEqual([tuple(r) for r in spark.sql(EXERCISES["15.1"]["solution"]).collect()], expected)
        self.course.spark, self.course.test_with_solutions = spark, False
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("15.1", ""))
            self.assertFalse(self.course.check(
                "15.1", "SELECT event_name, city, available, available AS stale_available FROM "
                        "IDENTIFIER(a8_event_availability) WHERE event_name IN ('Pipelines in Practice', "
                        "'Analytics Breakfast') ORDER BY event_name, city"))

    def test_notebook_standard_scope_and_navigation(self):
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "If it differs", "Cost boundary",
                       "has not been validated live"):
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 4)
        self.assertEqual({"15.a", "15.b"} - set(REFLECTIONS), set())
        for forbidden in ("A8.run", "A8.sql", "DROP ", "create_and_wait", "serving_endpoints.delete",
                          "delete_experiment", "delete_model", "delete_registered_model"):
            self.assertNotIn(forbidden, SOURCE)
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/14_evaluate_and_monitor.py"):
            self.assertIn("15_release_and_rollback", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 15", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))
        self.assertIn("15_release_and_rollback", (ROOT / "tests/live_smoke_stage2.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
