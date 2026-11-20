# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 3. Predict attendance, track it and put it to work
# MAGIC **By the end of this notebook you will have:**
# MAGIC - a classifier that predicts whether a confirmed booking turns up
# MAGIC - an MLflow run that records how it was trained and how well it did
# MAGIC - a versioned model in Unity Catalog with a `Champion` alias
# MAGIC - predictions for future bookings and an expected-turnout view for each event
# MAGIC - optionally, a live model serving endpoint
# MAGIC
# MAGIC **60–75 minutes:** environment 5 · MLflow 5 · features 10 · split and baseline 10 · train 15
# MAGIC · register 10 · score 15 · serving 10 (optional).
# MAGIC
# MAGIC **Before you start:** run Module 1. Module 2 is not needed; its governed copy is deliberately
# MAGIC not used for training.
# MAGIC
# MAGIC **What this writes:** a features table, an append-only predictions table, a forecast view,
# MAGIC an MLflow experiment, and a new model version each time you train.
# MAGIC Batch scoring needs no endpoint. **Serving is opt-in and can bill while it exists. Delete it before leaving.**

# COMMAND ----------
# MAGIC %md
# MAGIC ## 0. Prepare the Python environment (5 minutes)
# MAGIC Serverless notebooks come with many libraries already installed. We **pin exact versions** so that every
# MAGIC learner trains with the same code, and the saved model records versions that serving can reproduce later.
# MAGIC
# MAGIC `%pip install` installs packages **for this notebook only**. Other notebooks and other users are not affected.
# MAGIC
# MAGIC **Expect a red `ERROR: pip's dependency resolver…` message.** The environment also contains
# MAGIC `databricks-agents`, which wants a newer MLflow. This lesson does not use it, so the message is harmless.
# MAGIC The cell has worked if it ends with `Successfully installed … mlflow-3.6.0 …`.
# MAGIC A yellow notice that pandas changed version is the pin taking effect, not a fault.

# COMMAND ----------
# MAGIC %pip install mlflow==3.6.0 scikit-learn==1.7.2 pandas==2.2.3 typing_extensions==4.15.0

# COMMAND ----------
# MAGIC %md
# MAGIC Python has already loaded the old versions into memory. **Restarting Python** makes the next imports
# MAGIC use the versions you just installed. It also clears all variables, so we restart before doing anything else.
# MAGIC Then `_config` reloads the settings you saved in `00_setup` and recreates the `A8` helper.

# COMMAND ----------
# WHAT: restarts this notebook's Python process so the pinned packages are the ones imported.
# LOOK FOR: no output. The next cell will print your catalog, schema and tag.
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
# WHAT: imports the ML, tracking and Spark libraries used in this lesson.
# LOOK FOR: no output; imports make the names available to later cells.
from datetime import datetime, timezone

import mlflow
import numpy as np
import pandas as pd
from a8learn import COURSE_ID
from databricks.sdk import WorkspaceClient
from mlflow import MlflowClient
from mlflow.models import infer_signature
from pyspark.sql import functions as F
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Connect to MLflow (5 minutes)
# MAGIC **MLflow** keeps the evidence of machine learning work. Two parts matter today:
# MAGIC - **Tracking.** An *experiment* is a folder of *runs*. A run stores the settings, scores and files
# MAGIC   from one training attempt, so you can compare attempts and reproduce the one you chose.
# MAGIC - **Model registry.** Publish a trained model as numbered *versions*. Here the registry is
# MAGIC   **Unity Catalog**, so a model is governed like a table, with permissions and lineage.
# MAGIC
# MAGIC Your experiment lives in your workspace user folder; the printed link opens it.

# COMMAND ----------
# WHAT: points MLflow at Unity Catalog and selects your tagged experiment.
# LOOK FOR: MLflow 3.6.0 and your experiment path. A PermissionError means another course run uses this tag.
A8.require("events", "bookings")
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
w = WorkspaceClient()
A8.claim_experiment(client)  # refuse a foreign experiment; restore ours after cleanup
experiment = mlflow.set_experiment(A8.experiment_path)
A8.mark_experiment(client, experiment)
print("MLflow", mlflow.__version__, "| experiment:", experiment.name)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Decide what to predict, then build features (10 minutes)
# MAGIC **The prediction:** will a *confirmed booking* turn up? One row per booking. The **label** (the answer the
# MAGIC model learns) is 1 for attended and 0 for no-show. We are not predicting whether an event sells out.
# MAGIC
# MAGIC **The golden rule:** use only facts known **when the booking was made**. Feedback and attendance are only
# MAGIC known afterwards. Using them would *leak* the answer: the model would score brilliantly in testing and fail
# MAGIC in use.
# MAGIC
# MAGIC Two simplifications, because the data is synthetic:
# MAGIC - everyone in one booking attends together
# MAGIC - the data is frozen at 20 November 2026, so scheduled events have an **unknown** label (NULL), not 0
# MAGIC
# MAGIC **Predict before you run:** the query joins bookings to events, and both have a `status`.
# MAGIC Which one is filtered, and why are cancelled bookings left out?

# COMMAND ----------
# WHAT: builds one Delta table of booking-time features and labels.
# LOOK FOR: the CREATE TABLE result; scheduled events keep a null label because their outcome is unknown.
events = A8.t("events")
bookings = A8.t("bookings")
booking_features = A8.t("booking_features")
A8.guard("booking_features")
spark.sql(f"""CREATE OR REPLACE TABLE {booking_features} USING DELTA
COMMENT 'a8-databricks-learning booking-time attendance features'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')
AS SELECT b.booking_id, b.event_id,
b.tickets, b.ticket_type, b.organisation_type,
e.format, e.city, e.start_hour,
dayofweek(e.event_date) AS weekday,
datediff(e.event_date, b.booked_date) AS lead_days,
e.price_gbp, e.event_date, e.status AS event_status,
CAST(b.attended AS INT) AS label
FROM {bookings} b JOIN {events} e USING (event_id)
WHERE b.status = 'confirmed'
""")

# COMMAND ----------
# WHAT: summarises label availability in the new feature table.
# LOOK FOR: completed events have labels 0 or 1; scheduled events have a null label.
display(spark.sql(f"""SELECT event_status, label, count(*) AS bookings
FROM {booking_features} GROUP BY ALL"""))

# COMMAND ----------
# WHAT: checks that confirmed bookings have outcomes only for completed events.
# LOOK FOR: two green ticks; a failure means the feature query has leaked or lost the label contract.
unknown_completed = spark.table(booking_features).where(
    "event_status = 'completed' AND label IS NULL"
).count()
known_scheduled = spark.table(booking_features).where(
    "event_status = 'scheduled' AND label IS NOT NULL"
).count()
A8.expect(unknown_completed == 0, "Every completed-event booking has a known label.")
A8.expect(known_scheduled == 0, "Every scheduled-event booking has an unknown (null) label.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Split by time and set a baseline (10 minutes)
# MAGIC A model is only useful on bookings it has not seen. We **train on earlier events** and **test on the
# MAGIC 10 most recent completed events**, which mimics using the model on the future.
# MAGIC A random split would put bookings from the same event on both sides and make the test too easy.
# MAGIC
# MAGIC A **baseline** is the simplest honest guess: give every booking the overall attendance rate.
# MAGIC A model that cannot beat it is not worth deploying.
# MAGIC
# MAGIC **How we score:**
# MAGIC - **Log loss** (lower is better) rewards confident correct probabilities and punishes confident mistakes.
# MAGIC - **AUC** (0.5 is guessing, 1.0 is perfect) asks whether attendees get higher probabilities than no-shows.
# MAGIC - **Accuracy** can look good just by predicting "everyone attends", so never use it alone.
# MAGIC
# MAGIC Do not keep tweaking the model against this one test set; you would slowly fit the test instead of the problem.

# COMMAND ----------
# WHAT: loads the small feature table into pandas and splits it by event date.
# LOOK FOR: train, holdout and future booking counts, with no event shared by train and holdout.
frame = spark.table(A8.t("booking_features")).toPandas()  # scikit-learn needs pandas on one machine
categorical = ["ticket_type", "organisation_type", "format", "city"]
numeric = ["tickets", "start_hour", "weekday", "lead_days", "price_gbp"]
features = categorical + numeric  # identifiers, dates and the label are deliberately left out
frame[numeric] = frame[numeric].astype("float64")  # match training inputs to the model signature
completed = frame[frame.label.notna()].copy()
completed["label"] = completed.label.astype(int)
event_order = completed[["event_id", "event_date"]].drop_duplicates().sort_values(["event_date", "event_id"])
held_out = set(event_order.tail(10).event_id)
train = completed[~completed.event_id.isin(held_out)]
test = completed[completed.event_id.isin(held_out)]
future = frame[frame.event_status == "scheduled"].copy()
print(f"Train {len(train)}, holdout {len(test)}, future {len(future)} bookings")

# COMMAND ----------
# WHAT: checks the temporal split and the inputs available to the model.
# LOOK FOR: five green ticks; stop and fix the split if any check fails.
A8.expect(not set(train.event_id) & set(test.event_id), "No event appears in both train and holdout.")
A8.expect(train.event_date.max() <= test.event_date.min(), "Training events precede holdout events.")
A8.expect(future.label.isna().all() and len(future) > 0, "Future bookings are present and unlabelled.")
A8.expect(set(train.label) == {0, 1} and set(test.label) == {0, 1}, "Train and holdout contain both classes.")
forbidden = {"customer_email", "customer_name", "label", "event_id", "event_date", "attended"}
A8.expect(not forbidden & set(features), "Features contain no identifiers, outcomes or contact details.")

# COMMAND ----------
# WHAT: fits the simplest attendance-rate baseline and measures its log loss.
# LOOK FOR: the baseline probability and log loss; the model below must beat this number.
baseline = DummyClassifier(strategy="prior").fit(train[features], train.label)
baseline_p = baseline.predict_proba(test[features])[:, 1]
baseline_loss = log_loss(test.label, baseline_p)
print(f"Baseline attendance probability {train.label.mean():.3f}, holdout log loss {baseline_loss:.3f}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Train a transparent model and record the evidence (15 minutes)
# MAGIC Models need numbers, so we prepare the columns first:
# MAGIC - **One-hot encoding** turns a category such as `city` into 0/1 columns, one per city.
# MAGIC - **Standardisation** puts numbers such as price and lead time on a similar scale.
# MAGIC
# MAGIC A scikit-learn **Pipeline** chains preparation and the model. It learns the preparation from the
# MAGIC **training data only** and saves both together, so scoring later prepares data in exactly the same way.
# MAGIC **Logistic regression** is a simple, explainable classifier that outputs a probability.
# MAGIC
# MAGIC Inside `mlflow.start_run()` we log **parameters** (choices), **metrics** (scores), a small evaluation file
# MAGIC and the **model** itself with its *signature* (expected input columns and output shape).
# MAGIC
# MAGIC **Predict before you run:** will the model beat the baseline log loss you just printed? By a lot or a little?

# COMMAND ----------
# WHAT: defines the preparation and logistic-regression pipeline without fitting it yet.
# LOOK FOR: no output; unseen categories will be ignored rather than causing a scoring failure.
preprocess = ColumnTransformer([
    ("categories", OneHotEncoder(handle_unknown="ignore"), categorical),
    ("numbers", StandardScaler(), numeric),
])
pipeline = Pipeline([
    ("prepare", preprocess),
    ("classifier", LogisticRegression(max_iter=500, random_state=8)),
])

# COMMAND ----------
# WHAT: fits the pipeline and records parameters, metrics, limitations and the model in one MLflow run.
# LOOK FOR: four metrics and an experiment link; compare holdout_log_loss with baseline_log_loss.
with mlflow.start_run(run_name="booking-attendance-logistic") as run:
    mlflow.set_tags({**A8.course_tags, "evaluation": "last 10 completed events held out"})
    mlflow.log_params({"model": "logistic_regression", "seed": 8, "holdout_events": 10,
                       "train_bookings": len(train), "test_bookings": len(test)})
    pipeline.fit(train[features], train.label)
    probabilities = pipeline.predict_proba(test[features])[:, 1]
    metrics = {
        "holdout_accuracy": accuracy_score(test.label, probabilities >= 0.5),
        "holdout_auc": roc_auc_score(test.label, probabilities),
        "holdout_log_loss": log_loss(test.label, probabilities),
        "baseline_log_loss": baseline_loss,
    }
    mlflow.log_metrics(metrics)
    contract = {"features": features, "held_out_events": sorted(held_out), "snapshot": "2026-11-20",
                "limitations": ["synthetic data", "one temporal holdout", "party attends together",
                                "future bookings not yet made are excluded"]}
    mlflow.log_dict(contract, "evaluation_contract.json")
    example = train[features].head(5)
    model_info = mlflow.sklearn.log_model(
        pipeline, name="attendance", input_example=example,
        signature=infer_signature(example, pipeline.predict_proba(example)),
        pyfunc_predict_fn="predict_proba",
        pip_requirements=["scikit-learn==1.7.2", "pandas==2.2.3", "numpy==1.26.4"],
    )
print(pd.Series(metrics))
A8.links(("Experiment: inspect this run", "experiment", experiment.experiment_id))

# COMMAND ----------
# WHAT: checks whether the trained model improves on the baseline before registration.
# LOOK FOR: a green tick. A failure means investigate the model, not approve it for production.
A8.expect(
    metrics["holdout_log_loss"] < baseline_loss,
    "The model beats the attendance-rate baseline on holdout log loss.",
)

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** open the experiment, then the run. Find the parameters, the metrics, `evaluation_contract.json`,
# MAGIC and under the model: its signature and input example.
# MAGIC Why is AUC alone not enough to forecast how many people will turn up?
# MAGIC
# MAGIC **Your turn (optional):** add `C=0.1` to `LogisticRegression(...)` above (smaller `C` means a simpler model),
# MAGIC run the training cells again and compare the two runs in the experiment's chart view. Both runs are kept.
# MAGIC
# MAGIC ## 5. Register a version and assign an alias (10 minutes)
# MAGIC A run is **evidence**. A **registered model version** is a **release**: a numbered, permission-controlled copy
# MAGIC that other people and jobs can use. Each registration adds a version; old versions are never overwritten.
# MAGIC
# MAGIC An **alias** such as `Champion` is a movable label pointing at one version. Code that loads
# MAGIC `@Champion` gets whichever version the label points to, so you can promote or roll back without changing code.
# MAGIC An alias is not proof of quality; the evidence in the run is.

# COMMAND ----------
# WHAT: publishes this run as a new model version and points Champion at it.
# LOOK FOR: Champion → version N; N increases each time you train again.
model_name = A8.model_name
A8.claim_model(client, w)
version = mlflow.register_model(model_info.model_uri, model_name)
client.set_registered_model_alias(model_name, "Champion", version.version)
A8.links(("Registered model: versions and aliases", "model", "attendance_model"))
print(f"Champion → version {version.version}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Score future bookings with the released model (15 minutes)
# MAGIC We load **Champion from the registry**, not the `pipeline` variable in memory. That tests what other
# MAGIC people would actually use. `spark_udf` applies the model in Spark and returns
# MAGIC **[P(no-show), P(attend)]** for each booking.
# MAGIC
# MAGIC Each scoring run **appends** its predictions with `model_version` and `scored_at`, preserving evidence.
# MAGIC The forecast uses only the latest score for each booking, so retraining never double-counts bookings.
# MAGIC Expected turnout is **sum of tickets × P(attend)** over confirmed bookings made so far.
# MAGIC It excludes bookings not yet made and gives no uncertainty range.
# MAGIC
# MAGIC **Predict before you run:** can expected attendees exceed confirmed tickets? Why not?

# COMMAND ----------
# WHAT: creates a Spark UDF for Champion and scores the scheduled bookings in Spark.
# LOOK FOR: no output until the next cell; numeric inputs are cast to match the saved model signature.
released_version = client.get_model_version_by_alias(model_name, "Champion").version
predict_attendance = mlflow.pyfunc.spark_udf(
    spark, f"models:/{model_name}@Champion", result_type="array<double>"
)
future_spark = spark.table(booking_features).where(F.col("event_status") == "scheduled")
for name in numeric:
    future_spark = future_spark.withColumn(name, F.col(name).cast("double"))
# Serverless rejects cache(); this small batch is evaluated once for checks and once for the append.
scored = future_spark.withColumn("probabilities", predict_attendance(F.struct(*features)))

# COMMAND ----------
# WHAT: checks the released model's row count, probability range and probability sums before saving.
# LOOK FOR: two green ticks. Nothing is appended if either check fails.
probability_check = scored.select(
    F.col("probabilities")[0].alias("no_show"),
    F.col("probabilities")[1].alias("attendance"),
)
valid = (
    F.col("no_show").isNotNull() & F.col("attendance").isNotNull()
    & F.col("no_show").between(0, 1) & F.col("attendance").between(0, 1)
    & (F.abs(F.col("no_show") + F.col("attendance") - 1) < 0.000001)
)
score_summary = probability_check.agg(
    F.count("*").alias("rows"),
    F.sum(F.when(~valid, 1).otherwise(0)).alias("invalid"),
).first()
A8.expect(score_summary["rows"] == len(future), "Spark scoring returned one row per future booking.")
A8.expect(score_summary["invalid"] == 0, "Every score is a valid two-class probability pair.")

# COMMAND ----------
# WHAT: selects the attendance probability and labels this batch with its model version and timestamp.
# LOOK FOR: no output yet; the saved batch is displayed after the append check.
scored_at = datetime.now(timezone.utc)
current_predictions = (
    scored.select(
        "booking_id", "event_id", F.col("tickets").cast("int").alias("tickets"),
        F.col("probabilities")[1].alias("attendance_probability"),
    )
    .withColumn("model_version", F.lit(str(released_version)))
    .withColumn("scored_at", F.lit(scored_at))
)

# COMMAND ----------
# WHAT: creates the prediction history table if needed, or adds scored_at to an older course table.
# LOOK FOR: the six prediction columns; existing rows and their history are preserved.
predictions = A8.t("attendance_predictions")
A8.guard("attendance_predictions")
spark.sql(f"""CREATE TABLE IF NOT EXISTS {predictions} (
booking_id STRING, event_id STRING, tickets INT, attendance_probability DOUBLE,
model_version STRING, scored_at TIMESTAMP
) USING DELTA
COMMENT 'a8-databricks-learning appended probabilities for confirmed future bookings'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')""")
if "scored_at" not in spark.table(predictions).columns:
    spark.sql(f"ALTER TABLE {predictions} ADD COLUMNS (scored_at TIMESTAMP)")
print(spark.table(predictions).columns)

# COMMAND ----------
# WHAT: appends this batch without overwriting scores from earlier model versions.
# LOOK FOR: the append result; rerunning adds a new batch, while the forecast below uses only the latest.
current_predictions.write.mode("append").saveAsTable(predictions)

# COMMAND ----------
# WHAT: checks that this complete batch, and only this batch, was appended.
# LOOK FOR: one green tick with the expected future-booking count.
this_batch = spark.table(predictions).where(
    (F.col("model_version") == str(released_version)) & (F.col("scored_at") == F.lit(scored_at))
)
A8.expect(this_batch.count() == len(future), "The appended batch contains every future booking exactly once.")

# COMMAND ----------
# WHAT: displays the persisted predictions from this model version and scoring batch.
# LOOK FOR: five rows with attendance_probability, model_version and scored_at.
display(this_batch.orderBy("booking_id").limit(5))

# COMMAND ----------
# WHAT: builds the forecast view from the latest prediction for each booking.
# LOOK FOR: one row per scheduled event; older model versions cannot inflate expected attendance.
event_forecast = A8.t("event_forecast")
A8.guard("event_forecast")
spark.sql(f"""CREATE OR REPLACE VIEW {event_forecast}
COMMENT 'a8-databricks-learning expected turnout from latest scores for existing bookings only'
AS WITH ranked AS (
SELECT p.*, row_number() OVER (
PARTITION BY booking_id ORDER BY scored_at DESC NULLS LAST, CAST(model_version AS INT) DESC
) AS score_rank FROM {predictions} p
)
SELECT e.event_id, e.event_name, e.event_date, e.capacity,
coalesce(sum(p.tickets), 0) AS confirmed_tickets,
coalesce(sum(p.tickets * p.attendance_probability), 0) AS expected_attendees
FROM {events} e LEFT JOIN ranked p ON e.event_id = p.event_id AND p.score_rank = 1
WHERE e.status = 'scheduled'
GROUP BY e.event_id, e.event_name, e.event_date, e.capacity""")

# COMMAND ----------
# WHAT: displays expected turnout for each scheduled event.
# LOOK FOR: 12 rows, with expected_attendees between zero and confirmed_tickets.
display(spark.sql(f"SELECT * FROM {event_forecast} ORDER BY event_date"))

# COMMAND ----------
# WHAT: checks the forecast grain and bounds independently of the scoring code.
# LOOK FOR: two green ticks and a link to inspect forecast lineage.
forecast_rows = spark.table(event_forecast).count()
invalid_forecasts = spark.table(event_forecast).where(
    "expected_attendees < 0 OR expected_attendees > confirmed_tickets"
).count()
A8.expect(forecast_rows == 12, "The forecast contains all 12 scheduled events.")
A8.expect(invalid_forecasts == 0, "Every expected attendance lies between zero and confirmed tickets.")
A8.links(("Forecast: inspect upstream lineage", "table", "event_forecast"))

# COMMAND ----------
# MAGIC %md
# MAGIC ### Exercise 3.1: write the forecast yourself
# MAGIC Using only the predictions table, first find the latest score for each booking with `row_number()`.
# MAGIC Then return `event_id` and `expected_attendees` (the sum of tickets × attendance_probability),
# MAGIC one row per event, ordered by `event_id`. Use `IDENTIFIER(a8_attendance_predictions)` as the table name.
# MAGIC Put your SQL between the triple quotes and run the cell. A blank answer shows a hint.

# COMMAND ----------
# WHAT: checks your SQL against the course's answer on your own tables.
# LOOK FOR: a green correct card. A8.solution("3.1") shows a worked answer if you are stuck.
answer_3_1 = """"""
A8.check("3.1", answer_3_1)

# COMMAND ----------
# MAGIC %md
# MAGIC **UI exercise:** add a bar chart of confirmed tickets and expected attendees by event.
# MAGIC Which difference might an organiser misread? Explain: expected attendance covers only bookings we already have.
# MAGIC What extra model would you need to predict bookings not yet made?
# MAGIC
# MAGIC ## 7. Optional: deploy a real-time endpoint (10 minutes)
# MAGIC Batch scoring runs when you choose and needs no endpoint. **Model serving** instead keeps the model
# MAGIC available behind a REST API, so an app can ask for a prediction at any moment. That convenience has a cost.
# MAGIC
# MAGIC Set `deploy_serving` to **yes** only if your workspace allows custom model serving and you accept the cost.
# MAGIC - It uses the smallest size and *scale to zero*, which reduces but does not guarantee zero cost.
# MAGIC - Provisioning can take many minutes. Free Edition quotas differ; a capability error does not affect
# MAGIC   batch scoring.
# MAGIC - It only creates a new endpoint; it never updates an existing one. If interrupted, delete the endpoint in
# MAGIC   **Serving** or run `99_pause_and_cleanup`. Do not keep retrying quota errors.

# COMMAND ----------
# WHAT: if you opted in, creates an endpoint pinned to the tested model version.
# LOOK FOR: endpoint details, or Serving skipped. The endpoint can bill until you delete it.
if A8.gate("deploy_serving", "Create a billable attendance serving endpoint?"):
    from databricks.sdk.service.serving import EndpointCoreConfigInput, EndpointTag, ServedEntityInput

    w.serving_endpoints.create_and_wait(
        name=A8.endpoint_name,
        config=EndpointCoreConfigInput(name=A8.endpoint_name, served_entities=[
            ServedEntityInput(entity_name=model_name, entity_version=str(version.version),
                              workload_size="Small", scale_to_zero_enabled=True)
        ]),
        tags=[EndpointTag(key=k, value=v) for k, v in A8.course_tags.items()],
    )
    A8.links(("Your endpoint: inspect status/logs, then delete", "endpoint", A8.endpoint_name))
else:
    print("Serving skipped. The registered model and batch forecast are the core outcome.")

# COMMAND ----------
# WHAT: if serving is enabled, sends two bookings to the endpoint in dataframe_split format.
# LOOK FOR: two pairs of probabilities from the online model.
if A8.gate("deploy_serving", "Create a billable attendance serving endpoint?"):
    sample_ids = future.booking_id.head(2).tolist()
    payload = {"dataframe_split": future[features].head(2).to_dict(orient="split")}
    response = w.api_client.do("POST", f"/serving-endpoints/{A8.endpoint_name}/invocations", body=payload)
    online = np.asarray(response["predictions"])
    print(online)

# COMMAND ----------
# WHAT: compares online probabilities with this Spark batch for the same two booking IDs.
# LOOK FOR: one green tick when serving is enabled; otherwise a reminder that serving was skipped.
if A8.gate("deploy_serving", "Create a billable attendance serving endpoint?"):
    batch_rows = this_batch.where(F.col("booking_id").isin(sample_ids)).collect()
    batch_by_id = {row.booking_id: row.attendance_probability for row in batch_rows}
    batch = np.array([batch_by_id[booking_id] for booking_id in sample_ids])
    matches = online.shape == (2, 2) and np.allclose(online[:, 1], batch, atol=1e-6)
    A8.expect(matches, "Online probabilities match the Spark batch for the same two bookings.")
else:
    print("Serving check skipped because no endpoint was requested.")

# COMMAND ----------
# MAGIC %md
# MAGIC **UI alternative:** Serving → Create endpoint → choose this model and version → Small → scale to zero.
# MAGIC Use exactly the name printed below, and add the two course tags (`a8learn_course`, `a8learn_tag`).
# MAGIC Query it with the model's input example, look at its permissions and logs, then **delete** it.
# MAGIC Stopping compute is not enough. Serving this scikit-learn model is not a GenAI call; Module 4 adds those.
# MAGIC
# MAGIC ## Recap
# MAGIC Name the unit of prediction, the time-based split, the baseline, the run, the model version, the alias and
# MAGIC the batch output. **Which of these are fixed evidence, and which can move?**
# MAGIC (The run, version and appended batch are fixed; the alias and forecast view change when you retrain.)
# MAGIC
# MAGIC **Stop here for Stage 1.** Modules 4–8 are planned, not yet supplied. Remove any serving endpoint now.

# COMMAND ----------
# WHAT: prints your endpoint's name and summarises what you built.
# LOOK FOR: the module-complete card and the cleanup notebook name.
print("Optional endpoint name:", A8.endpoint_name)
A8.next_step(["Booking-time feature table and temporal holdout", "MLflow run with baseline and metrics",
              "UC model version and Champion alias", "Spark batch inference history and latest-score forecast"],
             "99_pause_and_cleanup", "Pause safely or remove only your course work")
