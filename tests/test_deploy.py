"""Offline checks for Module 12 and the packaged agent. No MLflow, workspace, model or endpoint is contacted.

MLflow, the Databricks SDK client and Spark are replaced by recording stand-ins, so these tests show what the
notebook would send and in what order, not how Databricks behaves. The agent code itself is real and is checked
against independent Python on the shipped data.
"""
import contextlib
import importlib
import io
import json
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
from a8learn import COURSE_ID, OBJECTS, Config, Course, agent_core
from a8learn.exercises import EXERCISES, REFLECTIONS
from test_agents import ROOT, StandInSpark, rows_of

NOTEBOOK = ROOT / "notebooks/12_deploy_and_govern.py"
SOURCE = NOTEBOOK.read_text(encoding="utf-8")
WRITES = ("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE", "MERGE")


def snapshot_from(spark):
    chunks = [dict(r) for r in spark.db.execute("SELECT doc_name, section, content FROM doc_chunks ORDER BY 1, 2")]
    seats = [dict(r) for r in spark.db.execute(
        "SELECT event_name, city, event_date, status, available FROM event_availability")]
    return {"chunks": chunks, "seats": seats}


class FakeMlflow(ModuleType):
    """Records every write the notebook asks MLflow to make."""

    def __init__(self):
        super().__init__("mlflow")
        self.calls = []
        self.logged = {}
        self.pyfunc = SimpleNamespace(log_model=self.log_model, load_model=self.load_model)
        outer = self

        class MlflowClient:
            def __getattr__(self, name):
                def record(*args, **kwargs):
                    outer.calls.append((name, args, kwargs))
                return record

        self.MlflowClient = MlflowClient

    def set_registry_uri(self, uri):
        self.calls.append(("set_registry_uri", (uri,), {}))

    def set_experiment(self, path):
        self.calls.append(("set_experiment", (path,), {}))
        return SimpleNamespace(experiment_id="1", name=path)

    @contextlib.contextmanager
    def start_run(self, run_name=None):
        self.calls.append(("start_run", (run_name,), {}))
        yield SimpleNamespace(info=SimpleNamespace(run_id="r1"))

    def set_tags(self, tags):
        self.calls.append(("set_tags", (tags,), {}))

    def log_params(self, params):
        self.calls.append(("log_params", (params,), {}))

    def log_metric(self, key, value):
        self.calls.append(("log_metric", (key, value), {}))

    def log_model(self, **kwargs):
        self.logged = kwargs
        self.calls.append(("log_model", (), kwargs))
        return SimpleNamespace(model_uri="runs:/r1/agent")

    def register_model(self, uri, name):
        self.calls.append(("register_model", (uri, name), {}))
        return SimpleNamespace(version="1")

    def load_model(self, uri):
        self.calls.append(("load_model", (uri,), {}))
        snapshot = json.loads(open(self.logged["artifacts"]["snapshot"], encoding="utf-8").read())

        class Loaded:
            metadata = SimpleNamespace(signature="question: string -> answer, status, steps")

            def predict(self, frame):
                results = [agent_core.answer(snapshot, q) for q in frame["question"]]
                return pd.DataFrame({"answer": [r["answer"] for r in results]})

        return Loaded()


class FakeWorkspace:
    def __init__(self, user):
        self.user, self.endpoints, self.calls = user, {}, []
        self.snapshot = None
        self.serving_endpoints = SimpleNamespace(
            get=self.get, create_and_wait=self.create_and_wait, delete=self.delete,
            get_permissions=lambda _id: SimpleNamespace(access_control_list=[SimpleNamespace(
                user_name=user, group_name=None, service_principal_name=None,
                all_permissions=[SimpleNamespace(permission_level=SimpleNamespace(value="CAN_MANAGE"))])]))
        self.api_client = SimpleNamespace(do=self.do)

    def get(self, name):
        from databricks.sdk.errors import NotFound
        if name not in self.endpoints:
            raise NotFound("none")
        return self.endpoints[name]

    def create_and_wait(self, name, config, tags):
        self.calls.append(("create_and_wait", name, config, tags))
        self.endpoints[name] = SimpleNamespace(
            id="ep1", creator=self.user, tags=tags, config=SimpleNamespace(served_entities=config.served_entities))

    def delete(self, name):
        self.calls.append(("delete", name))
        self.endpoints.pop(name)

    def do(self, method, path, body=None, query=None):
        if path.startswith("/api/2.1/unity-catalog/models/"):  # read-only governance lookups
            return {"owner": self.user, "aliases": [{"alias_name": "Champion", "version_num": 1}]}
        if path.startswith("/api/2.1/unity-catalog/permissions/"):
            return {"privilege_assignments": []}
        self.calls.append(("do", method, path, body))
        results = [agent_core.answer(self.snapshot, r["question"]) for r in body["dataframe_records"]]
        return {"predictions": [{"answer": r["answer"], "status": r["status"], "steps": ",".join(r["steps"])}
                                for r in results]}


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "offline12", "synthetic@example.com",
                                    "https://example.com"), answers="solutions")

    def run_lesson(self, existing_endpoint=False, **approvals):
        self.spark = StandInSpark(self.course, lambda prompt: None)
        self.addCleanup(self.spark.db.close)
        self.course.spark = self.spark
        self.mlflow = FakeMlflow()
        self.w = FakeWorkspace(self.course.cfg.user)
        self.w.snapshot = snapshot_from(self.spark)
        if existing_endpoint:
            self.w.endpoints[self.course.agent_endpoint_name] = SimpleNamespace(
                id="x", creator=self.course.cfg.user, config=SimpleNamespace(served_entities=[]),
                tags=[SimpleNamespace(key=k, value=v) for k, v in self.course.course_tags.items()])

        class Dbutils:
            library = SimpleNamespace(restartPython=lambda: None)

        gates = {"register_agent": False, "deploy_agent": False, "delete_agent_endpoint": False, **approvals}
        namespace = {"A8": self.course, "spark": self.spark, "dbutils": Dbutils, "ROOT": ROOT,
                     "display": lambda *_: None}
        with patch.dict(sys.modules, {"mlflow": self.mlflow}), \
             patch("databricks.sdk.WorkspaceClient", return_value=self.w), \
             patch.object(self.course, "require"), patch.object(self.course, "claim_experiment"), \
             patch.object(self.course, "mark_experiment"), patch.object(self.course, "claim_model"), \
             patch.object(self.course, "links"), \
             patch.object(self.course, "gate", lambda name, label: gates[name]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            exec(compile(SOURCE, str(NOTEBOOK), "exec"), namespace)
        self.output = out.getvalue()
        return namespace

    # ----- the packaged agent -----
    def test_packaged_agent_matches_the_module_9_baseline(self):
        namespace = self.run_lesson()
        local = namespace["local"]
        self.assertEqual([r["status"] for r in local], ["answered"] * 5)
        # 'take over my seat' ranks the wrong section first: the same single miss as the notebook agent in Module 9
        self.assertEqual(namespace["flags"], [True, True, False, True, True])
        self.assertIn("Grounded 4/5", self.output)

    def test_agent_core_guardrails_and_step_cap(self):
        snapshot = snapshot_from(StandInSpark(self.course, lambda prompt: None))
        self.assertIn("Unknown tool", agent_core.run_tool(snapshot, "drop_table", {"query": "x"})["error"])
        self.assertIn("error", agent_core.run_tool(snapshot, "search_docs", {"query": "a"}))
        self.assertIn("error", agent_core.run_tool(snapshot, "search_docs", {"query": "refund", "k": "1"}))
        self.assertIn("error", agent_core.run_tool(snapshot, "search_docs", "refund"))
        self.assertEqual(agent_core.check_availability(snapshot, "no such event"), [])
        with patch.object(agent_core, "rules_decide",
                          lambda s, t, trace: {"tool": "search_docs", "args": {"query": "refund"}}):
            stopped = agent_core.answer(snapshot, "anything")
        self.assertEqual((stopped["status"], len(stopped["steps"])), ("stopped: step cap reached", 4))

    def test_agent_core_uses_only_the_snapshot_not_other_data(self):
        snapshot = {"chunks": [], "seats": [{"event_name": "Only Event", "city": "X", "event_date": "2027-01-01",
                                             "status": "scheduled", "available": 3}]}
        result = agent_core.answer(snapshot, "How many seats are left for Only Event?")
        self.assertIn("3 seats left", result["answer"])

    def test_wrapper_loads_the_snapshot_and_returns_one_row_per_question(self):
        recorded = {}
        fake = ModuleType("mlflow")
        fake.models = SimpleNamespace(set_model=lambda model: recorded.setdefault("model", model))
        pyfunc = ModuleType("mlflow.pyfunc")
        pyfunc.PythonModel = type("PythonModel", (), {})
        sys_modules = {"mlflow": fake, "mlflow.pyfunc": pyfunc}
        with patch.dict(sys.modules, sys_modules), patch.object(sys, "path", [str(ROOT / "lib/a8learn")] + sys.path):
            sys.modules.pop("agent_model", None)
            module = importlib.import_module("agent_model")
            sys.modules.pop("agent_model", None)
        model = recorded["model"]
        self.assertIsInstance(model, module.A8Agent)
        snapshot = {"chunks": [], "seats": [{"event_name": "Only Event", "city": "X", "event_date": "2027-01-01",
                                             "status": "scheduled", "available": 3}]}
        path = ROOT / ".local-validation" / "wrapper-snapshot.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        self.addCleanup(path.unlink)
        model.load_context(SimpleNamespace(artifacts={"snapshot": str(path)}))
        frame = model.predict(None, pd.DataFrame({"question": ["Seats for Only Event?", "weather?"]}))
        self.assertEqual(list(frame.columns), ["answer", "status", "steps"])
        self.assertEqual(len(frame), 2)
        self.assertIn("3 seats left", frame["answer"][0])

    # ----- the notebook -----
    def test_default_run_writes_and_serves_nothing(self):
        namespace = self.run_lesson()
        self.assertEqual(self.mlflow.calls, [("set_registry_uri", ("databricks-uc",), {})])
        self.assertEqual(self.w.calls, [])
        self.assertEqual([q for q in self.spark.statements if q.lstrip().upper().startswith(WRITES)], [])
        self.assertIsNone(namespace["version"])
        self.assertFalse(namespace["endpoint_ready"])
        self.assertIn("Serving skipped", self.output)

    def test_snapshot_is_taken_from_the_tables_and_written_to_a_temporary_file(self):
        namespace = self.run_lesson()
        snapshot = namespace["snapshot"]
        self.assertEqual(len(snapshot["chunks"]), 32)
        self.assertEqual(len(snapshot["seats"]), len(rows_of("events.csv")))
        self.assertNotIn(str(ROOT), str(namespace["snapshot_path"]))
        self.assertTrue(namespace["snapshot_path"].exists())

    def test_register_logs_the_agent_with_its_code_snapshot_and_a_champion_alias(self):
        namespace = self.run_lesson(register_agent=True)
        logged = self.mlflow.logged
        self.assertTrue(logged["python_model"].endswith("agent_model.py"))
        self.assertEqual([p.split("\\")[-1].split("/")[-1] for p in logged["code_paths"]], ["agent_core.py"])
        self.assertEqual(set(logged["artifacts"]), {"snapshot"})
        self.assertEqual(list(logged["input_example"].columns), ["question"])
        names = [c[0] for c in self.mlflow.calls]
        self.assertLess(names.index("log_model"), names.index("register_model"))
        alias = next(c for c in self.mlflow.calls if c[0] == "set_registered_model_alias")
        self.assertEqual(alias[1], (self.course.agent_model_name, "Champion", "1"))
        tags = next(c for c in self.mlflow.calls if c[0] == "set_tags")[1][0]
        self.assertEqual(tags["a8learn_course"], COURSE_ID)
        self.assertEqual(tags["a8learn_tag"], "offline12")
        self.assertIsNotNone(namespace["loaded_answers"])  # the released model answered identically (A8.expect)
        self.assertEqual(self.w.calls, [])  # registering never creates an endpoint

    def test_deploy_pins_the_registered_version_tags_the_endpoint_and_matches_local_answers(self):
        namespace = self.run_lesson(register_agent=True, deploy_agent=True)
        create = next(c for c in self.w.calls if c[0] == "create_and_wait")
        _, name, config, tags = create
        self.assertEqual(name, "a8-offline12-agent")
        entity = config.served_entities[0]
        self.assertEqual((entity.entity_name, entity.entity_version, entity.workload_size,
                          entity.scale_to_zero_enabled), (self.course.agent_model_name, "1", "Small", True))
        self.assertEqual({t.key: t.value for t in tags}, self.course.course_tags)
        query = next(c for c in self.w.calls if c[0] == "do")
        self.assertEqual(query[2], "/serving-endpoints/a8-offline12-agent/invocations")
        self.assertEqual(len(query[3]["dataframe_records"]), 5)
        self.assertEqual([p["answer"] for p in namespace["served"]], [r["answer"] for r in namespace["local"]])
        self.assertIn("Who can use it", self.output)
        self.assertIn("Aliases: {'Champion': 1}", self.output)
        self.assertIn("none beyond ownership", self.output)
        self.assertEqual([c for c in self.w.calls if c[0] == "delete"], [])  # deletion has its own switch

    def test_deploy_without_a_registered_version_does_nothing(self):
        self.run_lesson(deploy_agent=True)
        self.assertEqual(self.w.calls, [])
        self.assertIn("Register the model first", self.output)

    def test_existing_owned_endpoint_is_left_alone_and_a_foreign_one_stops_the_lesson(self):
        namespace = self.run_lesson(existing_endpoint=True, register_agent=True, deploy_agent=True)
        self.assertEqual([c for c in self.w.calls if c[0] == "create_and_wait"], [])
        self.assertIn("already exists and is yours", self.output)
        self.assertTrue(namespace["endpoint_ready"])
        with self.assertRaises(PermissionError):
            with patch.object(FakeWorkspace, "get", lambda self_, name: SimpleNamespace(
                    creator="other@example.com", tags=[], id="x", config=None)):
                self.run_lesson(register_agent=True, deploy_agent=True)

    def test_delete_removes_only_the_owned_agent_endpoint(self):
        self.run_lesson(register_agent=True, deploy_agent=True, delete_agent_endpoint=True)
        deletes = [c for c in self.w.calls if c[0] == "delete"]
        self.assertEqual(deletes, [("delete", "a8-offline12-agent")])
        self.assertIn("Deleted.", self.output)

    def test_delete_with_nothing_to_delete_is_a_message(self):
        self.run_lesson(delete_agent_endpoint=True)
        self.assertEqual([c for c in self.w.calls if c[0] == "delete"], [])
        self.assertIn("no agent endpoint of yours", self.output)

    def test_exercise_solutions_match_independent_python(self):
        self.run_lesson()
        booked = {}
        for b in rows_of("bookings.csv"):
            if b["status"] == "confirmed":
                booked[b["event_id"]] = booked.get(b["event_id"], 0) + b["tickets"]
        left = [(e["event_name"], e["city"], e["capacity"] - booked.get(e["event_id"], 0))
                for e in rows_of("events.csv") if e["status"] == "scheduled"]
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["12.1"]["solution"]).collect()]
        self.assertEqual(rows, sorted((r for r in left if r[2] < 40), key=lambda r: (r[2], r[0], r[1])))
        self.assertTrue(rows)
        by_city = {}
        for _, city, seats in left:
            by_city[city] = by_city.get(city, 0) + seats
        rows = [tuple(r) for r in self.spark.sql(EXERCISES["12.2"]["solution"]).collect()]
        self.assertEqual(rows, sorted(by_city.items(), key=lambda kv: (-kv[1], kv[0])))

    def test_blank_and_naive_exercise_answers_fail(self):
        self.run_lesson()
        self.course.test_with_solutions = False
        naive = ("SELECT event_name, city, available FROM IDENTIFIER(a8_event_availability) "
                 "WHERE available < 40 ORDER BY available, event_name, city")  # forgets the scheduled filter
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.course.check("12.1", ""))
            self.assertFalse(self.course.check("12.1", naive))

    def test_notebook_standard_scope_and_navigation(self):
        self.assertEqual(OBJECTS["agent_model"], ("model", "12_deploy_and_govern"))
        text = SOURCE.replace("# MAGIC ", "")
        for phrase in ("**Where this sits:**", "Free first", "Terms in this lesson", "If it differs", "Cost boundary"):
            self.assertIn(phrase, text)
        self.assertEqual(len(re.findall(r'A8\.gate\("', SOURCE)), 3)
        self.assertEqual({"12.a", "12.b"} - set(REFLECTIONS), set())
        for forbidden in ("A8.run", "A8.sql", "delete_registered_model", "delete_model_version"):
            self.assertNotIn(forbidden, SOURCE)  # the model is removed by 99_pause_and_cleanup, not here
        for path in ("docs/index.md", "START_HERE.md", "notebooks/00_setup.py", "notebooks/09_agents.py"):
            self.assertIn("12_deploy_and_govern", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("Module 12", (ROOT / "docs/validation.md").read_text(encoding="utf-8"))


class AgentCleanupTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "smoke", "student@example.com", "https://example.com"))
        self.w, self.client = Mock(), Mock()
        from databricks.sdk.errors import NotFound
        self.NotFound = NotFound
        self.w.vector_search_indexes.get_index.side_effect = NotFound("none")
        self.w.vector_search_endpoints.get_endpoint.side_effect = NotFound("none")
        self.w.apps.get.side_effect = NotFound("none")
        self.w.pipelines.list_pipelines.return_value = []
        self.w.jobs.list.return_value = []
        self.mine = SimpleNamespace(creator=self.course.cfg.user, tags=[
            SimpleNamespace(key="a8learn_course", value=COURSE_ID), SimpleNamespace(key="a8learn_tag", value="smoke")])

    def test_agent_endpoint_is_deleted_for_its_owner(self):
        from a8learn.lifecycle import cleanup

        def get(name):
            if name == "a8-smoke-agent":
                return self.mine
            raise self.NotFound("none")

        self.w.serving_endpoints.get.side_effect = get
        result = cleanup(self.course, self.w, self.client, "smoke")
        self.assertTrue(result["agent_endpoint_deleted"])
        self.assertFalse(result["endpoint_deleted"])
        self.w.serving_endpoints.delete.assert_called_once_with("a8-smoke-agent")

    def test_foreign_agent_endpoint_stops_cleanup_before_any_delete(self):
        from a8learn.lifecycle import cleanup
        self.mine.creator = "other@example.com"
        self.w.serving_endpoints.get.side_effect = lambda name: self.mine
        with self.assertRaises(PermissionError):
            cleanup(self.course, self.w, self.client, "smoke")
        self.w.serving_endpoints.delete.assert_not_called()

    def test_full_cleanup_removes_the_agent_model_versions_and_aliases(self):
        from a8learn.lifecycle import cleanup

        class Missing(Exception):
            error_code = "RESOURCE_DOES_NOT_EXIST"

        agent = SimpleNamespace(name=self.course.agent_model_name, aliases={"Champion": "1"},
                                tags={"a8learn_course": COURSE_ID, "a8learn_tag": "smoke"})

        def get_model(name):
            if name == self.course.agent_model_name:
                return agent
            raise Missing()

        self.client.get_registered_model.side_effect = get_model
        self.client.get_experiment_by_name.return_value = None
        self.client.search_model_versions.return_value = [SimpleNamespace(version="1")]
        self.w.registered_models.get.return_value = SimpleNamespace(owner=self.course.cfg.user)
        self.w.serving_endpoints.get.side_effect = self.NotFound("none")
        fake_mlflow = SimpleNamespace(exceptions=SimpleNamespace(MlflowException=Missing))
        with patch.dict(sys.modules, {"mlflow": fake_mlflow}), \
             patch.object(self.course, "exists", return_value=False), patch.object(self.course, "guard"):
            result = cleanup(self.course, self.w, self.client, "smoke", tables=True)
        self.assertTrue(result["agent_model_deleted"])
        self.assertFalse(result["model_deleted"])
        self.client.delete_registered_model_alias.assert_called_once_with(self.course.agent_model_name, "Champion")
        self.client.delete_model_version.assert_called_once_with(self.course.agent_model_name, "1")
        self.client.delete_registered_model.assert_called_once_with(self.course.agent_model_name)

    def test_foreign_agent_model_is_refused(self):
        from a8learn.lifecycle import cleanup

        class Missing(Exception):
            error_code = "RESOURCE_DOES_NOT_EXIST"

        foreign = SimpleNamespace(name=self.course.agent_model_name, aliases={}, tags={})
        self.client.get_registered_model.side_effect = lambda name: foreign if "agent" in name else (_ for _ in ()
                                                                                                    ).throw(Missing())
        self.client.get_experiment_by_name.return_value = None
        self.w.registered_models.get.return_value = SimpleNamespace(owner=self.course.cfg.user)
        self.w.serving_endpoints.get.side_effect = self.NotFound("none")
        fake_mlflow = SimpleNamespace(exceptions=SimpleNamespace(MlflowException=Missing))
        with patch.dict(sys.modules, {"mlflow": fake_mlflow}), \
             patch.object(self.course, "exists", return_value=False), patch.object(self.course, "guard"):
            with self.assertRaises(PermissionError):
                cleanup(self.course, self.w, self.client, "smoke", tables=True)
        self.client.delete_registered_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
