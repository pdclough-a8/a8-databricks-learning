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
assert A8.cfg.catalog == "workspace" and A8.cfg.schema == "default" and A8.cfg.tag.startswith("smoke")
assert A8.test_with_solutions
assert A8.sql("SELECT count(*) FROM {events}").first()[0] == 60
assert A8.sql("SELECT count(*) FROM {bookings}").first()[0] == 4204
assert A8.sql("SELECT count(*) FROM {feedback}").first()[0] == 395

import csv
from collections import Counter
from a8learn import OBJECTS
from a8learn.exercises import EXERCISES

with (ROOT / "data/raw/bookings.csv").open(encoding="utf-8", newline="") as f:
    bookings = list(csv.DictReader(f))
with (ROOT / "data/raw/events.csv").open(encoding="utf-8", newline="") as f:
    events = {e["event_id"]: e for e in csv.DictReader(f)}
expected_cities = Counter(events[b["event_id"]]["city"] for b in bookings
                          if events[b["event_id"]]["city"] in {"Leeds", "Online"})
observed_cities = dict((r[0], r[1]) for r in A8.sql(
    "SELECT city, count(*) FROM {bookings_governed} GROUP BY city").collect())
assert observed_cities == expected_cities
assert A8.sql("SELECT count(*) FROM {bookings_governed} WHERE customer_email NOT LIKE '%***%'").first()[0] == 0
for exercise_id in EXERCISES:
    assert A8.check(exercise_id)

expected_future = [b for b in bookings if b["status"] == "confirmed"
                   and events[b["event_id"]]["status"] == "scheduled"]
assert A8.sql("SELECT count(*) FROM {attendance_predictions}").first()[0] == len(expected_future)
assert A8.sql("SELECT count(*) FROM {event_forecast}").first()[0] == 12
assert A8.sql("""SELECT count(*) FROM {event_forecast}
WHERE expected_attendees < 0 OR expected_attendees > confirmed_tickets""").first()[0] == 0
assert A8.sql("""SELECT count(*) FROM {events} VERSION AS OF 0
WHERE event_id = 'E149'""").first()[0] == 1
print("ACCEPTANCE: source counts, independent policy counts, five exercises, future row count, forecast bounds and history passed.")

# COMMAND ----------
import mlflow
from mlflow import MlflowClient
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
model_name = f"{A8.cfg.catalog}.{A8.cfg.schema}.{A8.name('attendance_model')}"
champion = client.get_model_version_by_alias(model_name, "Champion")
assert champion.status == "READY"
experiment = mlflow.get_experiment_by_name(A8.experiment_path)
run = client.search_runs([experiment.experiment_id], order_by=["start_time DESC"], max_results=1)[0]
print("METRICS:", run.data.metrics)
print("CHAMPION:", champion.version)
