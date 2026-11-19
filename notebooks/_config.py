# Databricks notebook source
# MAGIC %md
# MAGIC # Shared configuration, not a lesson
# MAGIC Each lesson runs this notebook. Settings are read from your saved JSON, not inherited widgets.
# MAGIC Nothing is created or deployed here. If settings are missing, run `00_setup`.

# COMMAND ----------
import sys
from pathlib import Path

_here = Path.cwd()
ROOT = next((p for p in [_here, *_here.parents]
             if (p / "lib" / "a8learn").is_dir() and (p / "data" / "raw").is_dir()), None)
if ROOT is None:
    raise RuntimeError("Keep the full repository together. Open this notebook in its Git folder.")
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from a8learn import Course

dbutils.widgets.text("config_profile", "default", "Saved settings profile")
dbutils.widgets.dropdown("answers", "", ["", "solutions"], "Instructor test answers")
_user = spark.sql("SELECT current_user()").first()[0]
A8 = Course.load(
    spark, _user, dbutils.widgets.get("config_profile"),
    display=display, display_html=displayHTML, dbutils=dbutils, root=ROOT,
    answers=dbutils.widgets.get("answers"),
)
if A8.cfg.user != _user:
    raise PermissionError("These settings belong to another user. Run 00_setup as yourself.")
A8.declare_variables()
print(f"A8 | {A8.cfg.catalog}.{A8.cfg.schema} | tag: {A8.cfg.tag}")
