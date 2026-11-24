import ast
import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from a8learn import Config, Course, OBJECTS, compare, config_path, derive_tag, quote, validate_tag
from a8learn.exercises import EXERCISES

spec = importlib.util.spec_from_file_location("generate", ROOT / "data/generate.py")
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config("workspace", "default", "learner8", "student@example.com", "https://example.com")
        self.course = Course(self.cfg)

    def test_validation(self):
        for tag in ["", "A", "a_", "1student", "a" * 13, "x';drop"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate_tag(tag)
        for catalog in ["system", "samples", "dbacademy"]:
            with self.assertRaises(ValueError):
                Config(catalog, "default", "ab", "", "").validate()
        self.assertEqual(derive_tag("42@example.com"), "learner42")
        self.assertEqual(quote("ai-training"), "`ai-training`")
        with self.assertRaises(ValueError):
            quote("catalog.schema")

    def test_all_names_are_exact_and_unique(self):
        names = [self.course.t(key) for key in OBJECTS]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(n.startswith("workspace.default.a8_learner8_") for n in names))
        with self.assertRaises(KeyError):
            self.course.t("unrelated")

    def test_fmt_keeps_non_course_braces(self):
        self.assertEqual(self.course.fmt("SELECT * FROM {events}"),
                         "SELECT * FROM workspace.default.a8_learner8_events")
        self.assertEqual(self.course.fmt('{"unknown": 2}'), '{"unknown": 2}')

    def test_persist_then_new_session_load_without_widgets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            with patch("a8learn.config_path", return_value=path):
                Course.save(self.cfg)
                loaded = Course.load(None, self.cfg.user)
            self.assertEqual(loaded.cfg.catalog, "workspace")
            self.assertEqual(loaded.cfg.tag, "learner8")
            self.assertEqual(json.loads(path.read_text())["schema"], "default")

    def test_missing_settings_is_actionable(self):
        with patch("a8learn.config_path", return_value=ROOT / "does-not-exist.json"):
            with self.assertRaisesRegex(FileNotFoundError, "00_setup"):
                Course.load(None, "student")

    def test_profiles_cannot_escape(self):
        for profile in ["../default", "", "UPPER"]:
            with self.assertRaises(ValueError):
                config_path("student", profile)

    def test_loader_does_not_run_setup(self):
        source = (ROOT / "notebooks/_config.py").read_text()
        self.assertIn("Course.load(", source)
        self.assertNotIn("%run ./00_setup", source)
        self.assertNotIn("Course.save(", source)
        self.assertNotIn("CREATE TABLE", source)

    def test_guard_rejects_other_owner_and_unmarked_own_object(self):
        self.course.spark = Mock()
        with patch.object(self.course, "_info", return_value="someone@example.com"):
            with self.assertRaises(PermissionError):
                self.course.guard("events")
        self.course.spark.sql.return_value.collect.return_value = [{"marker": "unrelated"}]
        with patch.object(self.course, "_info", return_value=self.cfg.user):
            with self.assertRaises(PermissionError):
                self.course.guard("events")
        marker = [{"marker": "a8-databricks-learning synthetic events"}]
        self.course.spark.sql.return_value.collect.return_value = marker
        with patch.object(self.course, "_info", return_value=self.cfg.user):
            self.course.guard("events")

    def test_expect_passes_or_raises_a_readable_error(self):
        self.assertIsNone(self.course.expect(True, "The result has the expected shape."))
        with self.assertRaisesRegex(AssertionError, "Expected 12 scheduled events"):
            self.course.expect(False, "Expected 12 scheduled events.")

    def test_reflect_needs_an_answer_and_every_reflection_is_used(self):
        self.assertFalse(self.course.reflect("0.1", "  "))
        self.assertTrue(self.course.reflect("0.1", "An event is one occasion."))
        source = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "notebooks").glob("*.py"))
        from a8learn.exercises import REFLECTIONS
        for key in REFLECTIONS:
            self.assertIn(f'A8.reflect("{key}"', source)

    def test_gate_defaults_to_no_and_preview_is_non_destructive(self):
        self.course.dbutils = Mock()
        self.course.dbutils.widgets.get.side_effect = RuntimeError("No widget")
        self.assertFalse(self.course.gate("deploy", "Deploy?"))

    def test_compare_checks_duplicates_order_and_shape(self):
        self.assertFalse(compare((["a"], [(1,), (1,)]), (["b"], [(1,)]))[0])
        self.assertFalse(compare((["a", "b"], [(1, 2)]), (["b"], [(1,)]))[0])
        self.assertTrue(compare((["a"], [(2,), (1,)]), (["b"], [(1,), (2,)]))[0])
        self.assertFalse(compare((["a"], [(2,), (1,)]), (["b"], [(1,), (2,)]), True)[0])


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.bookings, cls.feedback = generate.build()

    def test_generator_matches_shipped_files_exactly(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate, "OUT", Path(folder)):
            for rows, name in [(self.events, "events"), (self.bookings, "bookings"), (self.feedback, "feedback")]:
                generate.write(rows, name + ".csv")
                self.assertEqual((Path(folder) / (name + ".csv")).read_bytes(),
                                 (ROOT / "data/raw" / (name + ".csv")).read_bytes())
        self.assertEqual((len(self.events), len(self.bookings), len(self.feedback)), (60, 4204, 395))

    def test_keys_and_references(self):
        event_ids = {e["event_id"] for e in self.events}
        booking_ids = {b["booking_id"] for b in self.bookings}
        self.assertEqual(len(event_ids), len(self.events))
        self.assertEqual(len(booking_ids), len(self.bookings))
        self.assertTrue(all(b["event_id"] in event_ids for b in self.bookings))
        self.assertTrue(all(f["booking_id"] in booking_ids for f in self.feedback))

    def test_capacity_and_temporal_label_contract(self):
        events = {e["event_id"]: e for e in self.events}
        for e in self.events:
            booked = sum(b["tickets"] for b in self.bookings if b["event_id"] == e["event_id"])
            self.assertLessEqual(booked, e["capacity"])
        for b in self.bookings:
            self.assertTrue(b["customer_email"].endswith("@example.com"))
            self.assertLessEqual(b["booked_date"], "2026-11-20")
            known = events[b["event_id"]]["status"] == "completed" and b["status"] == "confirmed"
            self.assertEqual(b["attended"] in {"true", "false"}, known)
        self.assertEqual(sum(e["status"] == "scheduled" for e in self.events), 12)

    def test_supplied_sql_against_independent_python_aggregation(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        for name, rows in [("events", self.events), ("bookings", self.bookings)]:
            columns = list(rows[0])
            db.execute(f"CREATE TABLE {name} ({', '.join(columns)})")
            db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for c in columns)})",
                           [tuple(row.values()) for row in rows])
        expected = sorted((city, sum(e["city"] == city and e["status"] == "completed" for e in self.events))
                          for city in {e["city"] for e in self.events})
        query = re.sub(r"IDENTIFIER\(a8_(\w+)\)", r"\1", EXERCISES["1.1"]["solution"])
        self.assertEqual(db.execute(query).fetchall(), expected)
        scheduled = {e["event_id"] for e in self.events if e["status"] == "scheduled"}
        counts = {
            eid: sum(b["tickets"] for b in self.bookings if b["event_id"] == eid and b["status"] == "confirmed")
            for eid in scheduled
        }
        query = re.sub(r"IDENTIFIER\(a8_(\w+)\)", r"\1", EXERCISES["1.2"]["solution"])
        self.assertEqual(db.execute(query).fetchall(), sorted(counts.items()))

    def test_forecast_exercise_uses_only_latest_prediction_per_booking(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("""CREATE TABLE attendance_predictions (
            booking_id TEXT, event_id TEXT, tickets INT, attendance_probability REAL,
            model_version TEXT, scored_at TEXT)""")
        db.executemany("INSERT INTO attendance_predictions VALUES (?, ?, ?, ?, ?, ?)", [
            ("B1", "E1", 2, 0.25, "1", "2026-11-20 10:00:00"),
            ("B1", "E1", 2, 0.75, "2", "2026-11-20 11:00:00"),
            ("B2", "E1", 1, 0.50, "2", "2026-11-20 11:00:00"),
        ])
        query = re.sub(r"IDENTIFIER\(a8_(\w+)\)", r"\1", EXERCISES["5.1"]["solution"])
        self.assertEqual(db.execute(query).fetchall(), [("E1", 2.0)])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "smoke", "student@example.com", "https://example.com"))
        self.w, self.client = Mock(), Mock()
        self.w.serving_endpoints.get.return_value = SimpleNamespace(
            creator=self.course.cfg.user,
            tags=[SimpleNamespace(key="a8learn_course", value="a8-databricks-learning"),
                  SimpleNamespace(key="a8learn_tag", value="smoke")])

    def test_wrong_confirmation_does_nothing(self):
        from a8learn.lifecycle import cleanup
        with self.assertRaises(ValueError):
            cleanup(self.course, self.w, self.client, "wrong")
        self.w.serving_endpoints.get.assert_not_called()

    def test_endpoint_owner_and_tag_required(self):
        from a8learn.lifecycle import cleanup
        self.w.serving_endpoints.get.return_value.creator = "other@example.com"
        with self.assertRaises(PermissionError):
            cleanup(self.course, self.w, self.client, "smoke")
        self.w.serving_endpoints.delete.assert_not_called()

    def test_endpoint_only_never_touches_data(self):
        from a8learn.lifecycle import cleanup
        result = cleanup(self.course, self.w, self.client, "smoke")
        self.assertTrue(result["endpoint_deleted"])
        self.w.serving_endpoints.delete.assert_called_once_with("a8-smoke-attendance")
        self.client.delete_registered_model.assert_not_called()

    def test_absent_endpoint_is_idempotent(self):
        from a8learn.lifecycle import cleanup
        from databricks.sdk.errors import NotFound
        self.w.serving_endpoints.get.side_effect = NotFound("missing")
        result = cleanup(self.course, self.w, self.client, "smoke")
        self.assertFalse(result["endpoint_deleted"])

    def test_preflight_conflict_prevents_endpoint_deletion(self):
        from a8learn.lifecycle import cleanup
        with patch.object(self.course, "exists", return_value=True), \
             patch.object(self.course, "guard", side_effect=PermissionError("foreign")):
            with self.assertRaises(PermissionError):
                cleanup(self.course, self.w, self.client, "smoke", tables=True)
        self.w.serving_endpoints.delete.assert_not_called()

    def test_partial_and_repeated_full_cleanup_dependency_order(self):
        from a8learn.lifecycle import cleanup
        from databricks.sdk.errors import NotFound

        class MissingModel(Exception):
            error_code = "RESOURCE_DOES_NOT_EXIST"

        fake_mlflow = SimpleNamespace(exceptions=SimpleNamespace(MlflowException=MissingModel))
        self.client.get_registered_model.side_effect = MissingModel()
        self.client.get_experiment_by_name.return_value = None
        present = {"bookings_governed", "city_filter", "mask_email", "event_metrics",
                   "feedback", "bookings", "events", "raw"}
        dropped = []

        def drop(statement):
            key = next(key for key in present if statement.endswith(self.course.t(key)))
            present.remove(key)
            dropped.append(key)

        def remove_endpoint(_):
            self.w.serving_endpoints.get.side_effect = NotFound("removed")

        self.w.serving_endpoints.delete.side_effect = remove_endpoint
        with patch.dict(sys.modules, {"mlflow": fake_mlflow}), \
             patch.object(self.course, "exists", side_effect=lambda key: key in present), \
             patch.object(self.course, "guard"), patch.object(self.course, "run", side_effect=drop):
            first = cleanup(self.course, self.w, self.client, "smoke", tables=True)
            second = cleanup(self.course, self.w, self.client, "smoke", tables=True)
        self.assertEqual(first["data_objects_deleted"], 8)
        self.assertEqual(second["data_objects_deleted"], 0)
        self.assertFalse(second["endpoint_deleted"])
        self.assertLess(dropped.index("bookings_governed"), dropped.index("city_filter"))
        self.assertLess(dropped.index("bookings_governed"), dropped.index("mask_email"))
        for source in ["events", "bookings", "feedback"]:
            self.assertLess(dropped.index("event_metrics"), dropped.index(source))
        self.assertEqual(dropped[-1], "raw")

    def test_model_alias_versions_then_model_and_experiment(self):
        from a8learn.lifecycle import cleanup
        marker = {"a8learn_course": "a8-databricks-learning", "a8learn_tag": "smoke"}
        name = "workspace.default.a8_smoke_attendance_model"
        model = SimpleNamespace(tags=marker, name=name, aliases={"Champion": "1"})
        self.client.get_registered_model.return_value = model
        self.client.search_model_versions.return_value = [SimpleNamespace(version="1")]
        self.w.registered_models.get.return_value.owner = self.course.cfg.user
        self.client.get_experiment_by_name.return_value = SimpleNamespace(
            tags=marker, experiment_id="88", lifecycle_stage="active")
        with patch.dict(sys.modules, {"mlflow": SimpleNamespace()}), \
             patch.object(self.course, "exists", return_value=False):
            cleanup(self.course, self.w, self.client, "smoke", tables=True)
        names = [c[0] for c in self.client.mock_calls]
        self.assertLess(names.index("delete_registered_model_alias"), names.index("delete_model_version"))
        self.assertLess(names.index("delete_model_version"), names.index("delete_registered_model"))
        self.assertLess(names.index("delete_registered_model"), names.index("delete_experiment"))


class MlflowOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.course = Course(Config("workspace", "default", "learner8", "student@example.com", "https://example.com"))
        self.client, self.w = Mock(), Mock()
        self.mine = {"a8learn_course": "a8-databricks-learning", "a8learn_tag": "learner8"}

    def test_new_experiment_path_is_left_for_mlflow_to_create(self):
        self.client.get_experiment_by_name.return_value = None
        self.course.claim_experiment(self.client)
        self.client.restore_experiment.assert_not_called()

    def test_foreign_experiment_is_refused_and_own_deleted_one_restored(self):
        self.client.get_experiment_by_name.return_value = SimpleNamespace(
            tags={"a8learn_course": "a8-databricks-learning", "a8learn_tag": "other"},
            lifecycle_stage="active", experiment_id="1")
        with self.assertRaises(PermissionError):
            self.course.claim_experiment(self.client)
        self.client.get_experiment_by_name.return_value = SimpleNamespace(
            tags=self.mine, lifecycle_stage="deleted", experiment_id="7")
        self.course.claim_experiment(self.client)
        self.client.restore_experiment.assert_called_once_with("7")

    def test_mark_experiment_sets_both_tags(self):
        self.course.mark_experiment(self.client, SimpleNamespace(experiment_id="7"))
        self.assertEqual({c.args[1:] for c in self.client.set_experiment_tag.call_args_list},
                         set(self.mine.items()))

    def test_claim_model_creates_missing_and_checks_existing(self):
        class Missing(Exception):
            error_code = "RESOURCE_DOES_NOT_EXIST"

        self.client.get_registered_model.side_effect = Missing()
        self.course.claim_model(self.client, self.w)
        self.client.create_registered_model.assert_called_once_with(
            "workspace.default.a8_learner8_attendance_model", tags=self.mine)

        self.client.get_registered_model.side_effect = None
        self.client.get_registered_model.return_value = SimpleNamespace(tags={})
        with self.assertRaises(PermissionError):
            self.course.claim_model(self.client, self.w)
        self.client.get_registered_model.return_value = SimpleNamespace(tags=self.mine)
        self.w.registered_models.get.return_value.owner = "other@example.com"
        with self.assertRaises(PermissionError):
            self.course.claim_model(self.client, self.w)
        self.w.registered_models.get.return_value.owner = "student@example.com"
        self.course.claim_model(self.client, self.w)

    def test_other_registry_errors_are_not_swallowed(self):
        self.client.get_registered_model.side_effect = RuntimeError("network")
        with self.assertRaises(RuntimeError):
            self.course.claim_model(self.client, self.w)
        self.client.create_registered_model.assert_not_called()

class NotebookTests(unittest.TestCase):
    def test_sources_and_run_targets(self):
        paths = list((ROOT / "notebooks").glob("*.py"))
        self.assertEqual({p.stem for p in paths}, {
            "00_setup", "01_lakehouse_data", "03_descriptive_analytics", "04_diagnostic_analytics",
            "06_prescriptive_analytics", "02_governance", "07_genai",
            "05_predictive_ml", "08a_embeddings", "08b_rag", "99_pause_and_cleanup", "_config",
        })
        for path in paths:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, str(path))
            self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                             f"{path.name} must use A8.expect for runtime checks")
            self.assertNotRegex(source, r"A8\.(?:run|sql|fmt)\(",
                                f"{path.name} must use native Spark SQL with validated names")
            self.assertTrue(source.startswith("# Databricks notebook source\n"))
            for target in re.findall(r"^# MAGIC %run (.+)$", source, re.M):
                self.assertTrue((path.parent / (target + ".py")).is_file())
        ml = (ROOT / "notebooks/05_predictive_ml.py").read_text()
        self.assertIn('mlflow.pyfunc.spark_udf(', ml)
        self.assertIn('result_type="array<double>"', ml)
        self.assertNotIn(".cache()", ml)  # PERSIST TABLE is unsupported on serverless compute
        self.assertIn("baseline_log_loss", ml)
        self.assertIn('A8.gate("deploy_serving"', ml)

    def test_serving_config_builds_with_installed_sdk(self):
        from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput
        ml = (ROOT / "notebooks/05_predictive_ml.py").read_text(encoding="utf-8")
        self.assertIn("EndpointCoreConfigInput(name=A8.endpoint_name,", ml)
        config = EndpointCoreConfigInput(name="a8-x-attendance", served_entities=[
            ServedEntityInput(entity_name="c.s.m", entity_version="1",
                              workload_size="Small", scale_to_zero_enabled=True)])
        self.assertEqual(config.as_dict()["name"], "a8-x-attendance")

    def test_exercises_used_and_well_formed(self):
        source = "\n".join(p.read_text() for p in (ROOT / "notebooks").glob("*.py"))
        for key, exercise in EXERCISES.items():
            self.assertIn(f'A8.check("{key}"', source)
            self.assertEqual(set(exercise) - {"ordered"}, {"task", "hint", "solution", "explain"})

    def test_doc_links_and_nav(self):
        import yaml
        for path in [ROOT / "START_HERE.md", *list((ROOT / "docs").glob("*.md"))]:
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" not in link and not link.startswith("#"):
                    self.assertTrue((path.parent / link.split("#")[0]).exists(), f"{path}: {link}")
        config = yaml.safe_load((ROOT / "mkdocs.yml").read_text())
        for entry in config["nav"]:
            self.assertTrue((ROOT / "docs" / next(iter(entry.values()))).is_file())


if __name__ == "__main__":
    unittest.main()
