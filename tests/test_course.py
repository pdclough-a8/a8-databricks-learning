import ast
import contextlib
import io
import re
import sqlite3
import tomllib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yaml

from helpers import APP, ROOT, FakeSpark
from logic import load_events


class CourseTests(unittest.TestCase):
    def test_sources_parse_and_notebook_run_targets_exist(self):
        paths = list((ROOT / "notebooks").glob("*.py")) + list((ROOT / "solutions").glob("*.py"))
        self.assertEqual(len(paths), 6)
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertTrue(source.startswith("# Databricks notebook source\n"), path)
            self.assertIn("# COMMAND ----------", source)
            ast.parse(source, filename=str(path))
            for target in re.findall(r"^# MAGIC %run (.+)$", source, re.M):
                self.assertTrue((path.parent / (target.strip()+".py")).resolve().is_file(), target)
        for folder in (APP, ROOT / "course"):
            for path in folder.glob("*.py"):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_default_notebooks_do_not_mutate_or_construct_cloud_clients(self):
        values = {
            "catalog": "training", "schema": "authorised",
            "learner_tag": "learner07", "serving_endpoint": "",
        }
        dbutils = SimpleNamespace(
            widgets=SimpleNamespace(text=Mock(), get=values.__getitem__),
            library=SimpleNamespace(restartPython=Mock()),
        )
        setup = (ROOT / "notebooks/00_start_here.py").read_text(encoding="utf-8")
        for path in sorted((ROOT / "notebooks").glob("*.py")):
            spark = FakeSpark(True)
            env = {"dbutils": dbutils, "spark": spark, "display": Mock()}
            with self.subTest(path=path.name), patch("pathlib.Path.cwd", return_value=ROOT / "notebooks"), \
                 patch("databricks.sdk.WorkspaceClient", side_effect=AssertionError("Cloud client forbidden")), \
                 contextlib.redirect_stdout(io.StringIO()):
                # Emulate %run sharing globals; actual Databricks widget/magic behaviour needs live checks.
                exec(compile(setup, str(path), "exec"), env)
                if path.name != "00_start_here.py":
                    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), env)
            self.assertFalse(any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in spark.statements))
            for key in ("CREATE_MY_TABLE", "CREATE_MY_APP", "DEPLOY_MY_APP", "ALLOW_ONE_BILLABLE_REQUEST"):
                if key in env:
                    self.assertIs(env[key], False)
            if "CONFIRM_DELETE" in env:
                self.assertEqual(env["CONFIRM_DELETE"], "")

    def test_document_links_and_navigation(self):
        paths = [ROOT / "START_HERE.md"] + list((ROOT / "docs").rglob("*.md"))
        for path in paths:
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" not in link and not link.startswith("#"):
                    target = (path.parent / link.split("#")[0]).resolve()
                    self.assertTrue(target.exists(), f"{path}: {link}")
        config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
        def leaves(node):
            if isinstance(node, str):
                yield node
            elif isinstance(node, list):
                for child in node:
                    yield from leaves(child)
            elif isinstance(node, dict):
                for child in node.values():
                    yield from leaves(child)
        for target in leaves(config["nav"]):
            self.assertTrue((ROOT / "docs" / target).is_file())

    def test_app_is_a_self_contained_source_folder(self):
        config = yaml.safe_load((APP / "app.yaml").read_text())
        self.assertEqual(config["env"], [{"name": "SERVING_ENDPOINT", "valueFrom": "model"}])
        self.assertEqual(config["command"][:3], ["streamlit", "run", "app.py"])
        for path in ("app.py", "logic.py", "style.css", ".streamlit/config.toml",
                     "data/events.csv", "requirements.txt"):
            self.assertTrue((APP / path).is_file())
        self.assertNotIn("workspace_ops", (APP / "app.py").read_text())
        self.assertNotIn("spark", (APP / "app.py").read_text())
        theme = tomllib.loads((APP / ".streamlit/config.toml").read_text())
        self.assertIs(theme["global"]["developmentMode"], False)
        self.assertIs(theme["browser"]["gatherUsageStats"], False)

    def test_ui_supplied_query_directly(self):
        text = (ROOT / "docs/lessons/01-data.md").read_text(encoding="utf-8")
        query = text.split("```sql\n")[1].split("```")[0]
        query = "\n".join(line[4:] if line.startswith("    ") else line for line in query.splitlines())
        query = query.replace("YOUR_CATALOG.YOUR_SCHEMA.a8learn_YOUR_TAG_events", "events")
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE events(event_id, event_name, city, capacity, booked)")
        db.executemany("INSERT INTO events VALUES (:event_id,:event_name,:city,:capacity,:booked)", load_events())
        self.assertEqual(db.execute(query).fetchall(), [
            ("E101", "Analytics Breakfast", "Leeds", 18),
            ("E104", "Analytics Clinic", "Leeds", 22),
        ])

    def test_accent_contrast_and_no_external_fonts(self):
        def luminance(hex_colour):
            channels = [int(hex_colour[i:i+2], 16)/255 for i in (1, 3, 5)]
            linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]
            return sum(c*w for c, w in zip(linear, (.2126, .7152, .0722)))
        # Both text and control accent against the light and secondary app surfaces.
        for foreground in ("#a93614", "#1d2225"):
            for background in ("#ffffff", "#f2f2f2"):
                ratio = (luminance(background)+.05)/(luminance(foreground)+.05)
                self.assertGreaterEqual(ratio, 4.5)
        self.assertIn("font: false", (ROOT / "mkdocs.yml").read_text())
