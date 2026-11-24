"""Offline checks for Module 14. No MLflow, workspace, model or endpoint is contacted.

MLflow is replaced by a stand-in that really calls the predict function and the scorers, so the marks, the gate and
the order of writes are the notebook's own. These tests do not show how MLflow 3.6 or Databricks behaves: see
docs/validation.md for live status.
"""
import contextlib
import inspect
import io
import re
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "lib"))
sys.path.insert(0, str(ROOT_DIR / "tests"))
from a8learn import Config, Course, agent_core
from a8learn import evaluation as ev
from a8learn.exercises import EXERCISES, REFLECTIONS
from test_agents import ROOT, StandInSpark, rows_of
from test_deploy import snapshot_from

NOTEBOOK = ROOT / "notebooks/14_evaluate_and_monitor.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")


class FakeMlflow(ModuleType):
    """Runs evaluate for real (predict function, scorers, means) and records spans and every call it is asked for."""

    def __init__(self):
        super().__init__("mlflow")
        self.calls, self.runs, self.traces, self._stack = [], [], [], []
        outer = self

        class MlflowClient:
            def set_tag(self, run_id, key, value):
                outer.calls.append(("set_tag", run_id, key, value))

        def scorer(function):
            return SimpleNamespace(name=function.__name__, function=function)

        class Guidelines:
            def __init__(self, name, guidelines, model):
                self.name, self.guidelines, self.model = name, guidelines, model

        self.MlflowClient = MlflowClient
        self.genai = SimpleNamespace(evaluate=self.evaluate)
        self.scorers = ModuleType("mlflow.genai.scorers")
        self.scorers.scorer, self.scorers.Guidelines = scorer, Guidelines
        self.Guidelines = Guidelines

    def trace(self, name=None, span_type=None):
        def decorate(function):
            def wrapped(*args, **kwargs):
                if not self._stack:
                    self.traces.append([])
                self.traces[-1].append(SimpleNamespace(name=name, span_type=span_type))
                self._stack.append(name)
                try:
                    return function(*args, **kwargs)
                finally:
                    self._stack.pop()
            return wrapped
        return decorate

    def set_experiment(self, path):
        self.calls.append(("set_experiment", path))
        return SimpleNamespace(experiment_id="exp1")

    def evaluate(self, data, predict_fn, scorers):
        run_id = f"run{len(self.runs) + 1}"
        marks = {s.name: [] for s in scorers}
        for row in data:
            outputs = predict_fn(**row["inputs"])
            for s in scorers:
                if isinstance(s, self.Guidelines):
                    marks[s.name].append(1.0)
                    continue
                arguments = {"outputs": outputs, "expectations": row["expectations"]}
                wanted = inspect.signature(s.function).parameters
                marks[s.name].append(float(s.function(**{k: v for k, v in arguments.items() if k in wanted})))
        self.runs.append({"run_id": run_id, "scorers": scorers})
        self.calls.append(("evaluate", run_id, [s.name for s in scorers]))
        return SimpleNamespace(run_id=run_id, metrics={f"{k}/mean": sum(v) / len(v) for k, v in marks.items()})

    def search_traces(self, locations, max_results):
        self.calls.append(("search_traces", locations))
        # As in MLflow 3.6, the trace column is text: spans are only reachable through get_trace
        return pd.DataFrame({"trace_id": [str(i) for i in range(len(self.traces))],
                             "trace": ["{}"] * len(self.traces),
                             "state": ["OK"] * len(self.traces), "execution_duration": [5] * len(self.traces)})

    def get_trace(self, trace_id):
        return SimpleNamespace(data=SimpleNamespace(spans=self.traces[int(trace_id)]))


class FakeWorkspace:
    def __init__(self, user):
        self.user, self.endpoints, self.requests, self.snapshot = user, {}, [], None
        self.serving_endpoints = SimpleNamespace(get=self.get, create_and_wait=Mock(), delete=Mock())
        self.api_client = SimpleNamespace(do=self.do)

    def get(self, name):
        from databricks.sdk.errors import NotFound
        if name not in self.endpoints:
            raise NotFound("none")
        return self.endpoints[name]

    def do(self, method, path, body=None):
        self.requests.append((method, path, body))
        results = [agent_core.answer(self.snapshot, r["question"]) for r in body["dataframe_records"]]
        return {"predictions": [{"answer": r["answer"], "status": r["status"], "steps": ",".join(r["steps"])}
                                for r in results]}


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline14", "synthetic@example.com",
                                    "https://example.com"))
        spark = StandInSpark(self.course, lambda prompt: None)
        self.addCleanup(spark.db.close)
        self.snapshot = snapshot_from(spark)

    def test_rules_mark_a_correct_seat_answer_and_a_correct_refusal(self):
        name = next(r for r in self.snapshot["seats"] if r["status"] == "scheduled")
        answer = agent_core.answer(self.snapshot, f"How many seats are left for {name['event_name']}?")
        expected = ev.make_expectations("check_availability", str(name["available"]))
        self.assertEqual((ev.right_tool(answer, expected), ev.grounded(answer, expected), ev.finished(answer)),
                         (True, True, True))
        refusal = agent_core.answer(self.snapshot, "What is the weather forecast for the London event?")
        nothing = ev.make_expectations(None, None)
        self.assertEqual(nothing, {"expected_tool": "none", "fact": ""})
        self.assertTrue(ev.right_tool(refusal, nothing))

    def test_seat_rule_is_a_whole_number_not_a_substring(self):
        expected = ev.make_expectations("check_availability", "5")
        self.assertFalse(ev.grounded({"answer": "London, 2026-12-01: 15 seats left"}, expected))
        self.assertFalse(ev.grounded({"answer": "London, 2026-05-01: 7 seats left"}, expected))
        self.assertTrue(ev.grounded({"answer": "London, 2026-12-01: 5 seats left"}, expected))

    def test_wrong_tool_and_a_guess_instead_of_a_refusal_fail(self):
        docs = ev.make_expectations("search_docs", "x.md")
        self.assertFalse(ev.right_tool({"steps": ["check_availability"]}, docs))
        self.assertTrue(ev.right_tool({"steps": "search_docs"}, docs))  # the endpoint returns steps as one string
        self.assertFalse(ev.right_tool({"steps": []}, docs))
        self.assertFalse(ev.grounded({"answer": "It will rain."}, ev.make_expectations(None, None)))
        self.assertFalse(ev.finished({"status": "stopped: step cap reached"}))

    def test_stale_snapshot_changes_only_the_seat_figures(self):
        stale = ev.stale_snapshot(self.snapshot)
        self.assertEqual(stale["chunks"], self.snapshot["chunks"])
        self.assertTrue(all(s["available"] == o["available"] + 7
                            for s, o in zip(stale["seats"], self.snapshot["seats"], strict=True)))

    def test_traced_tools_wraps_each_tool_and_restores_the_originals(self):
        original = dict(agent_core.TOOLS)
        wrapped_calls = []

        def trace(name, span_type):
            def decorate(function):
                def wrapper(*args):
                    wrapped_calls.append((name, span_type))
                    return function(*args)
                return wrapper
            return decorate

        with ev.traced_tools(trace):
            agent_core.answer(self.snapshot, "Do I get my money back if I pull out ten days before?")
        self.assertEqual(wrapped_calls, [("search_docs", "TOOL")])
        self.assertEqual(agent_core.TOOLS, original)
        with self.assertRaises(RuntimeError), ev.traced_tools(trace):
            raise RuntimeError("boom")
        self.assertEqual(agent_core.TOOLS, original)

    def test_release_gate_decisions(self):
        base = {"grounded/mean": 0.8, "finished/mean": 1.0}
        self.assertEqual(ev.release_gate(base, dict(base)), {"passed": True, "reasons": []})
        self.assertTrue(ev.release_gate(base, {"grounded/mean": 1.0, "finished/mean": 1.0})["passed"])
        worse = ev.release_gate(base, {"grounded/mean": 0.6, "finished/mean": 1.0})
        self.assertFalse(worse["passed"])
        self.assertIn("grounded/mean fell from 0.80 to 0.60", worse["reasons"])
        self.assertTrue(ev.release_gate(base, {"grounded/mean": 0.75, "finished/mean": 1.0}, tolerance=0.1)["passed"])
        self.assertFalse(ev.release_gate(base, {"grounded/mean": 0.8, "finished/mean": 0.8})["passed"])
        self.assertFalse(ev.release_gate(base, {"grounded/mean": 0.8})["passed"])  # a missing metric is a failure
        self.assertFalse(ev.release_gate({"finished/mean": 0.5}, {"finished/mean": 0.5})["passed"])  # required is 1.0

    def test_trace_summary(self):
        self.assertEqual(ev.trace_summary([("OK", 10), ("TraceState.ERROR", 30), ("OK", None), ("OK", 20)]),
                         {"traces": 4, "failed": 1, "median_ms": 20.0, "slowest_ms": 30.0})
        self.assertEqual(ev.trace_summary([]), {"traces": 0, "failed": 0, "median_ms": None, "slowest_ms": None})


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline14", "synthetic@example.com",
                                    "https://example.com"), answers="solutions")

    def run_lesson(self, endpoint=False, endpoint_stale=False, **approvals):
        self.spark = StandInSpark(self.course, lambda prompt: None)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.mlflow = FakeMlflow()
        self.w = FakeWorkspace(self.course.cfg.user)
        self.w.snapshot = snapshot_from(self.spark)
        if endpoint_stale:
            self.w.snapshot = ev.stale_snapshot(self.w.snapshot)
        if endpoint:
            self.w.endpoints[self.course.agent_endpoint_name] = SimpleNamespace(
                id="x", creator=self.course.cfg.user,
                tags=[SimpleNamespace(key=k, value=v) for k, v in self.course.course_tags.items()])

        class Dbutils:
            library = SimpleNamespace(restartPython=lambda: None)

        gates = {"run_evaluation": False, "run_judge": False, "evaluate_endpoint": False, **approvals}
        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        self.claim, self.mark = Mock(), Mock()
        with patch.dict(sys.modules, {"mlflow": self.mlflow, "mlflow.genai": self.mlflow.genai,
                                      "mlflow.genai.scorers": self.mlflow.scorers}), \
             patch("databricks.sdk.WorkspaceClient", return_value=self.w), \
             patch.object(self.course, "require"), patch.object(self.course, "links"), \
             patch.object(self.course, "claim_experiment", self.claim), \
             patch.object(self.course, "mark_experiment", self.mark), \
             patch.object(self.course, "gate", lambda name, label: gates[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    def evaluations(self):
        return [c for c in self.mlflow.calls if c[0] == "evaluate"]

    def test_default_run_writes_nothing_and_scores_in_plain_python(self):
        namespace = self.run_lesson()
        self.assertEqual(self.mlflow.calls, [])
        self.assertEqual(self.w.requests, [])
        self.claim.assert_not_called()
        self.assertEqual([m[1] for m in namespace["plain"]], [True, True, False, True, True])  # grounded: 4 of 5
        self.assertIn("Totals: tool", self.output)
        self.assertIn("Skipped. The plain-Python marks above", self.output)

    def test_gated_run_blocks_the_stale_candidate_and_releases_the_refreshed_one(self):
        namespace = self.run_lesson(run_evaluation=True)
        self.assertEqual(len(self.evaluations()), 3)
        self.claim.assert_called_once()
        self.assertEqual(self.claim.call_args.args[1], self.course.evaluation_experiment_path)
        self.assertNotEqual(self.course.evaluation_experiment_path, self.course.experiment_path)
        self.assertIn(("set_experiment", self.course.evaluation_experiment_path), self.mlflow.calls)
        self.assertEqual(namespace["baseline"]["grounded/mean"], 0.8)
        self.assertEqual(namespace["candidate"]["finished/mean"], 1.0)
        self.assertLess(namespace["candidate"]["grounded/mean"], namespace["baseline"]["grounded/mean"])
        self.assertFalse(namespace["verdict"]["passed"])
        self.assertTrue(namespace["refreshed_verdict"]["passed"])
        self.assertIn("Gate: BLOCKED", self.output)
        self.assertIn("Gate: RELEASE", self.output)

    def test_runs_are_named_and_carry_the_course_tags(self):
        self.run_lesson(run_evaluation=True)
        tags = {}
        for call in self.mlflow.calls:
            if call[0] == "set_tag":
                tags.setdefault(call[1], {})[call[2]] = call[3]
        self.assertEqual([t["mlflow.runName"] for t in tags.values()],
                         ["baseline", "candidate-stale-snapshot", "candidate-refreshed-snapshot"])
        for run_tags in tags.values():
            self.assertEqual({k: run_tags[k] for k in self.course.course_tags}, self.course.course_tags)

    def test_traces_hold_an_agent_span_and_a_tool_span_and_the_monitoring_summary_is_clean(self):
        namespace = self.run_lesson(run_evaluation=True)
        self.assertEqual(len(self.mlflow.traces), 15)
        names = [(s.name, s.span_type) for s in self.mlflow.traces[0]]
        self.assertEqual(names[0], ("support_agent", "AGENT"))
        self.assertIn(names[1][0], {"check_availability", "search_docs"})
        self.assertEqual(namespace["summary"], {"traces": 15, "failed": 0, "median_ms": 5.0, "slowest_ms": 5.0})
        self.assertEqual(set(agent_core.TOOLS), {"search_docs", "check_availability"})  # originals restored

    def test_judge_is_gated_and_names_the_chat_model_explicitly(self):
        self.run_lesson(run_evaluation=True)
        self.assertEqual(len(self.evaluations()), 3)
        self.assertIn("Skipped: no judge requests were made.", self.output)
        self.run_lesson(run_evaluation=True, run_judge=True)
        judge = self.mlflow.runs[-1]["scorers"]
        self.assertEqual(len(judge), 1)
        self.assertEqual(judge[0].model, "databricks:/databricks-meta-llama-3-3-70b-instruct")
        self.assertEqual(len(self.evaluations()), 4)
        self.run_lesson(run_judge=True)
        self.assertEqual(self.evaluations(), [])
        self.assertIn("Skipped: run the baseline first.", self.output)

    def test_endpoint_test_needs_an_existing_endpoint_and_never_creates_one(self):
        self.run_lesson(run_evaluation=True, evaluate_endpoint=True)
        self.assertEqual(self.w.requests, [])
        self.assertIn("no agent endpoint of yours to test", self.output)
        self.run_lesson(run_evaluation=True, evaluate_endpoint=True, endpoint=True)
        self.assertEqual(len(self.w.requests), 5)
        self.assertTrue(all(r[:2] == ("POST", f"/serving-endpoints/{self.course.agent_endpoint_name}/invocations")
                            for r in self.w.requests))
        self.assertIn("Gate: RELEASE", self.output.split("endpoint:")[1])
        self.w.serving_endpoints.create_and_wait.assert_not_called()
        self.w.serving_endpoints.delete.assert_not_called()

    def test_a_stale_endpoint_is_blocked_by_the_gate_not_by_an_error(self):
        namespace = self.run_lesson(run_evaluation=True, evaluate_endpoint=True, endpoint=True, endpoint_stale=True)
        self.assertEqual(namespace["endpoint_means"]["finished/mean"], 1.0)
        self.assertFalse(namespace["endpoint_verdict"]["passed"])
        self.assertTrue(any("grounded" in r for r in namespace["endpoint_verdict"]["reasons"]))

    def test_endpoint_without_the_baseline_does_not_send_requests(self):
        self.run_lesson(evaluate_endpoint=True, endpoint=True)
        self.assertEqual(self.w.requests, [])
        self.assertIn("Skipped: run the baseline first.", self.output)

    def test_exercise_solution_matches_independent_python_and_naive_answers_fail(self):
        spark = StandInSpark(self.course, lambda prompt: None)
        self.addCleanup(spark.db.close)
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        expected = sorted((e["event_name"], e["city"], e["capacity"] - booked.get(e["event_id"], 0))
                          for e in rows_of("events.csv")
                          if e["status"] == "scheduled" and e["event_name"] in {"Pipelines in Practice",
                                                                                 "Analytics Breakfast"})
        self.assertGreaterEqual(len(expected), 2)
        self.assertEqual([tuple(r) for r in spark.sql(EXERCISES["14.1"]["solution"]).collect()], expected)
        self.course.spark, self.course.test_with_solutions = spark, False
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("14.1", ""))
            self.assertFalse(self.course.check(
                "14.1", "SELECT event_name, city, available FROM IDENTIFIER(a8_event_availability) WHERE event_name "
                        "IN ('Pipelines in Practice', 'Analytics Breakfast') ORDER BY event_name, city"))

    def test_notebook_standard_scope_and_navigation(self):
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "If it differs", "Cost boundary",
                       "validated live on Free Edition on 24 November 2026"):
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 3)
        self.assertEqual({"14.a", "14.b"} - set(REFLECTIONS), set())
        for forbidden in ("A8.run", "A8.sql", "DROP ", "create_and_wait", "serving_endpoints.delete",
                          "delete_experiment"):
            self.assertNotIn(forbidden, SOURCE)
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/11_interactive_app.py"):
            self.assertIn("14_evaluate_and_monitor", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 14", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))
        self.assertIn("evaluate", (ROOT / "tests/live_smoke_stage2.py").read_text(encoding="utf-8"))


class EvaluationCleanupTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "smoke", "student@example.com", "https://example.com"))
        self.w, self.client = Mock(), Mock()
        from databricks.sdk.errors import NotFound
        self.w.vector_search_indexes.get_index.side_effect = NotFound("none")
        self.w.vector_search_endpoints.get_endpoint.side_effect = NotFound("none")
        self.w.apps.get.side_effect = NotFound("none")
        self.w.serving_endpoints.get.side_effect = NotFound("none")
        self.w.pipelines.list_pipelines.return_value = []
        self.w.jobs.list.return_value = []

        class Missing(Exception):
            error_code = "RESOURCE_DOES_NOT_EXIST"

        self.client.get_registered_model.side_effect = Missing()
        self.fake_mlflow = SimpleNamespace(exceptions=SimpleNamespace(MlflowException=Missing))
        self.attendance = SimpleNamespace(experiment_id="1", lifecycle_stage="active", tags=self.course.course_tags)
        self.client.get_experiment_by_name.side_effect = lambda path: {
            self.course.experiment_path: self.attendance,
            self.course.evaluation_experiment_path: self.evaluation}.get(path)

    def clean(self, tables=True):
        from a8learn.lifecycle import cleanup
        with patch.dict(sys.modules, {"mlflow": self.fake_mlflow}), \
             patch.object(self.course, "exists", return_value=False), patch.object(self.course, "guard"):
            return cleanup(self.course, self.w, self.client, "smoke", tables=tables)

    def test_both_course_experiments_are_deleted_and_nothing_else(self):
        self.evaluation = SimpleNamespace(experiment_id="2", lifecycle_stage="active", tags=self.course.course_tags)
        result = self.clean()
        self.assertTrue(result["evaluation_experiment_deleted"])
        self.assertEqual([c.args for c in self.client.delete_experiment.call_args_list], [("1",), ("2",)])

    def test_a_foreign_evaluation_experiment_stops_cleanup_before_any_delete(self):
        self.evaluation = SimpleNamespace(experiment_id="2", lifecycle_stage="active", tags={"a8learn_course": "other"})
        with self.assertRaises(PermissionError):
            self.clean()
        self.client.delete_experiment.assert_not_called()

    def test_already_deleted_or_absent_is_idempotent_and_experiments_stay_without_the_tables_option(self):
        self.evaluation = SimpleNamespace(experiment_id="2", lifecycle_stage="deleted", tags=self.course.course_tags)
        self.clean()
        self.assertEqual([c.args for c in self.client.delete_experiment.call_args_list], [("1",)])
        self.client.delete_experiment.reset_mock()
        self.evaluation = None
        self.assertFalse(self.clean()["evaluation_experiment_deleted"])
        self.client.delete_experiment.reset_mock()
        self.evaluation = SimpleNamespace(experiment_id="2", lifecycle_stage="active", tags=self.course.course_tags)
        self.clean(tables=False)
        self.client.delete_experiment.assert_not_called()

    def test_claim_experiment_checks_the_path_it_is_given(self):
        foreign = SimpleNamespace(experiment_id="9", lifecycle_stage="active", tags={})
        client = Mock()
        client.get_experiment_by_name.return_value = foreign
        with self.assertRaises(PermissionError) as raised:
            self.course.claim_experiment(client, self.course.evaluation_experiment_path)
        self.assertIn(self.course.evaluation_experiment_path, str(raised.exception))
        client.get_experiment_by_name.assert_called_with(self.course.evaluation_experiment_path)


if __name__ == "__main__":
    unittest.main()
