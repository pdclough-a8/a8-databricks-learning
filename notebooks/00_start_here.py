# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | Ready to build
# MAGIC **Start:** read `docs/start.md` in your full course copy. Attach authorised Python compute.
# MAGIC This notebook reads local fixtures and schema metadata only. Compute itself may bill.
# MAGIC Fill the four widgets, then run the configuration cell again.
# MAGIC Use your assigned existing catalog/schema and unique lowercase learner tag (max 16).
# MAGIC Leave endpoint blank for data/simulation only. No token, host or profile belongs here.

# COMMAND ----------
for key in ("catalog", "schema", "learner_tag", "serving_endpoint"):
    dbutils.widgets.text(key, "", key)

# COMMAND ----------
from pathlib import Path
import sys

ROOT = next(
    (p for p in (Path.cwd(), *Path.cwd().parents)
     if (p / "app" / "event_assistant" / "logic.py").is_file()),
    None,
)
if ROOT is None:
    raise ValueError("Open this notebook inside a full course Git folder or uploaded course folder.")
for folder in (ROOT / "app" / "event_assistant", ROOT / "course"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
from logic import load_events, names, ownership_marker, with_availability
from workspace_ops import check_table, cleanup, deploy_app, ensure_app, ensure_table

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
TAG = dbutils.widgets.get("learner_tag").strip()
ENDPOINT = dbutils.widgets.get("serving_endpoint").strip()
TABLE, APP_NAME = names(CATALOG, SCHEMA, TAG)
MARKER = ownership_marker(TAG)
EVENTS = load_events()
print({"table": TABLE, "app": APP_NAME, "ownership_marker": MARKER})
display(spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}").select("tableName"))
print("Schema metadata is readable. This does not prove create rights or app/model availability.")

# COMMAND ----------
# MAGIC %md
# MAGIC **Check:** you recognise the destination, marker and six synthetic records below.
# MAGIC No table or app has been created. Record names privately in your progress log.
# MAGIC **Next:** `01_explore_events`. To pause, use `docs/operations.md`.

# COMMAND ----------
display(spark.createDataFrame(with_availability(EVENTS)))
