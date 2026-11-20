# Databricks notebook source
# MAGIC %md
# MAGIC # Maintainer acceptance, not a learner lesson
# MAGIC Run only after the authorised Stage 1 smoke run. Reads only the smoke-tagged `a8_smoke*_*` objects.

# COMMAND ----------
# MAGIC %pip install mlflow-skinny==3.6.0 typing_extensions==4.15.0

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ../notebooks/_config $config_profile="stage1_smoke" $answers="solutions"

# COMMAND ----------
# WHAT: imports libraries used by the independent acceptance checks.
# LOOK FOR: no output.
import csv
from collections import Counter

import mlflow
from mlflow import MlflowClient

# COMMAND ----------
# WHAT: checks the smoke namespace and source-table row counts.
# LOOK FOR: five green ticks.
A8.expect(A8.cfg.catalog == "workspace" and A8.cfg.schema == "default", "Acceptance uses workspace.default.")
A8.expect(A8.cfg.tag.startswith("smoke") and A8.test_with_solutions, "Acceptance uses smoke solutions.")
for key, expected in [("events", 60), ("bookings", 4204), ("feedback", 395)]:
    actual = spark.table(A8.t(key)).count()
    A8.expect(actual == expected, f"{key} contains the expected {expected} source rows.")

# COMMAND ----------
# WHAT: derives expected policy results directly from the shipped CSV files.
# LOOK FOR: two green ticks for independent city counts and email masking.
with (ROOT / "data/raw/bookings.csv").open(encoding="utf-8", newline="") as f:
    bookings = list(csv.DictReader(f))
with (ROOT / "data/raw/events.csv").open(encoding="utf-8", newline="") as f:
    events = {e["event_id"]: e for e in csv.DictReader(f)}
expected_cities = Counter(
    events[b["event_id"]]["city"] for b in bookings
    if events[b["event_id"]]["city"] in {"Leeds", "Online"}
)
governed = A8.t("bookings_governed")
observed_cities = {r[0]: r[1] for r in spark.sql(
    f"SELECT city, count(*) FROM {governed} GROUP BY city"
).collect()}
unmasked = spark.sql(
    f"SELECT count(*) FROM {governed} WHERE customer_email NOT LIKE '%***%'"
).first()[0]
A8.expect(observed_cities == expected_cities, "Governed city counts match an independent CSV aggregation.")
A8.expect(unmasked == 0, "No unmasked customer email is visible through the governed table.")

# COMMAND ----------
# WHAT: runs the original Stage 1 exercise solutions against the smoke tables.
# LOOK FOR: a green tick for each exercise.
# live_smoke does not run Module 1b; never claim its SQL or UI checkpoints passed here.
for exercise_id in ("1.1", "1.2", "2.1", "2.2", "3.1"):
    A8.expect(A8.check(exercise_id), f"Exercise {exercise_id} matches its independent solution.")

# COMMAND ----------
# WHAT: checks the latest prediction per booking and forecast bounds after append-based scoring.
# LOOK FOR: five green ticks, including one latest prediction per booking and two appended batches.
expected_future = [
    b for b in bookings if b["status"] == "confirmed"
    and events[b["event_id"]]["status"] == "scheduled"
]
predictions = A8.t("attendance_predictions")
latest = spark.sql(f"""WITH ranked AS (
SELECT p.*, row_number() OVER (
PARTITION BY booking_id ORDER BY scored_at DESC NULLS LAST, CAST(model_version AS INT) DESC
) AS score_rank FROM {predictions} p
) SELECT * FROM ranked WHERE score_rank = 1""")
forecast = spark.table(A8.t("event_forecast"))
invalid = forecast.where("expected_attendees < 0 OR expected_attendees > confirmed_tickets").count()
A8.expect(latest.count() == len(expected_future), "Latest predictions cover every confirmed future booking once.")
A8.expect(
    spark.table(predictions).count() == 2 * len(expected_future),
    "Retraining appends a second complete prediction batch without replacing the first.",
)
A8.expect(latest.where("scored_at IS NULL").count() == 0, "Every latest prediction records its scoring time.")
A8.expect(forecast.count() == 12, "The forecast contains all 12 scheduled events.")
A8.expect(invalid == 0, "Every forecast is bounded by zero and confirmed tickets.")

# COMMAND ----------
# WHAT: checks that Delta version zero still contains the event used in the time-travel lesson.
# LOOK FOR: one green tick.
events_table = A8.t("events")
original = spark.sql(f"SELECT count(*) FROM {events_table} VERSION AS OF 0 WHERE event_id = 'E149'").first()[0]
A8.expect(original == 1, "Delta version zero retains the original E149 row.")

# COMMAND ----------
# WHAT: checks Champion and prints the latest run's recorded metrics.
# LOOK FOR: READY, the holdout metrics and the Champion version.
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
champion = client.get_model_version_by_alias(A8.model_name, "Champion")
A8.expect(champion.status == "READY", "The Champion model version is ready.")
experiment = mlflow.get_experiment_by_name(A8.experiment_path)
run = client.search_runs([experiment.experiment_id], order_by=["start_time DESC"], max_results=1)[0]
print("METRICS:", run.data.metrics)
print("CHAMPION:", champion.version)
print("ACCEPTANCE: source, policies, exercises, latest predictions, forecast, history and registry passed.")
