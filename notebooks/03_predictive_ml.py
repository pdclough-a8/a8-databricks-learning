# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 3. Predict attendance, track it and put it to work
# MAGIC **Outcome:** a tracked classifier, a versioned Unity Catalog model with a `Champion` alias,
# MAGIC batch-scored future bookings and an event turnout forecast. Optional: a live model serving request.
# MAGIC **60–75 minutes:** features 10 · split/baseline 10 · train/track 15 · registry 10 · score/UI 15 · serving 10 optional.
# MAGIC Requires Module 1. Module 2's governed sandbox is intentionally not the model's source.
# MAGIC Writes four course data objects, an MLflow experiment and a registered model version on each training run.
# MAGIC Batch inference needs no endpoint. **Serving is opt-in and can bill while provisioned. Delete it before leaving.**

# COMMAND ----------
# MAGIC %pip install mlflow==3.6.0 scikit-learn==1.7.2 pandas==2.2.3 typing_extensions==4.15.0

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
A8.require("events", "bookings")
import mlflow
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from mlflow import MlflowClient
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, roc_auc_score, log_loss

mlflow.set_registry_uri("databricks-uc")
experiment = mlflow.get_experiment_by_name(A8.experiment_path)
if experiment and (experiment.tags.get("a8learn_course") != "a8-databricks-learning" or
                   experiment.tags.get("a8learn_tag") != A8.cfg.tag):
    raise PermissionError("Existing experiment is not marked as this course run. Choose another tag.")
if experiment and experiment.lifecycle_stage == "deleted":
    MlflowClient().restore_experiment(experiment.experiment_id)
mlflow.set_experiment(A8.experiment_path)
experiment = mlflow.get_experiment_by_name(A8.experiment_path)
MlflowClient().set_experiment_tag(experiment.experiment_id, "a8learn_course", "a8-databricks-learning")
MlflowClient().set_experiment_tag(experiment.experiment_id, "a8learn_tag", A8.cfg.tag)
print("MLflow", mlflow.__version__)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Define the prediction, then features (10 minutes)
# MAGIC We predict **whether a confirmed booking attends**, not whether an event sells out.
# MAGIC Each booking's party is treated as attending together, an explicit simplification of the synthetic data.
# MAGIC Use only facts available at booking time. Feedback and eventual attendance would leak the answer.
# MAGIC The data is frozen at 20 November 2026; scheduled events have unknown labels, not zero labels.
# MAGIC This is a classroom example, not a validated operational forecasting product.
# MAGIC
# MAGIC Read the join. Which status belongs to the booking and which to the event?
# MAGIC Why do we exclude cancelled bookings? Why might one person's repeated bookings make a random split optimistic?

# COMMAND ----------
from a8learn import COURSE_ID
A8.guard("booking_features")
A8.run(f"""CREATE OR REPLACE TABLE {{booking_features}} USING DELTA
COMMENT 'a8-databricks-learning booking-time attendance features'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')
AS SELECT b.booking_id, b.event_id, b.tickets, b.ticket_type, b.organisation_type,
e.format, e.city, e.start_hour, dayofweek(e.event_date) AS weekday,
datediff(e.event_date, b.booked_date) AS lead_days,
e.price_gbp, e.event_date, e.status AS event_status,
CAST(b.attended AS INT) AS label
FROM {{bookings}} b JOIN {{events}} e USING (event_id)
WHERE b.status = 'confirmed'""")
display(A8.sql("SELECT event_status, label, count(*) AS bookings FROM {booking_features} GROUP BY ALL"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Split chronologically and establish a baseline (10 minutes)
# MAGIC Train on earlier events and evaluate on later **completed** events. The scheduled set is for future scoring.
# MAGIC A random row split can put bookings from the same event on both sides, making the test easier than deployment.
# MAGIC We hold out the final 10 completed events, not a random sample of their bookings.
# MAGIC Do not tune repeatedly against this holdout. Real deployment would also require validation over several time windows.
# MAGIC Accuracy can reward "everyone attends"; log loss tests probability quality, and AUC tests ranking.

# COMMAND ----------
frame = spark.table(A8.t("booking_features")).toPandas()
categorical = ["ticket_type", "organisation_type", "format", "city"]
numeric = ["tickets", "start_hour", "weekday", "lead_days", "price_gbp"]
features = categorical + numeric
frame[numeric] = frame[numeric].astype("float64")
completed = frame[frame.label.notna()].copy()
completed["label"] = completed.label.astype(int)
event_order = completed[["event_id", "event_date"]].drop_duplicates().sort_values(["event_date", "event_id"])
held_out = set(event_order.tail(10).event_id)
train = completed[~completed.event_id.isin(held_out)]
test = completed[completed.event_id.isin(held_out)]
future = frame[frame.event_status == "scheduled"].copy()
assert not set(train.event_id) & set(test.event_id)
assert train.event_date.max() <= test.event_date.min()
assert future.label.isna().all() and len(future) > 0
assert not {"customer_email", "customer_name", "label", "event_id", "event_date"} & set(features)
assert set(train.label) == {0, 1} and set(test.label) == {0, 1}

baseline = DummyClassifier(strategy="prior").fit(train[features], train.label)
baseline_p = baseline.predict_proba(test[features])[:, 1]
baseline_loss = log_loss(test.label, baseline_p)
print(f"Train {len(train)}, holdout {len(test)}, future {len(future)} bookings")
print(f"Baseline attendance probability {train.label.mean():.3f}, holdout log loss {baseline_loss:.3f}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Train a transparent pipeline and track the evidence (15 minutes)
# MAGIC One-hot encoding converts categories to indicator columns. Standardisation puts numeric features on comparable scales.
# MAGIC A scikit-learn Pipeline fits preprocessing on **training data only** and packages it with the classifier.
# MAGIC MLflow records parameters, metrics, artefacts and a model signature (input/output schema), not just a pickle file.
# MAGIC A run that completes is not automatically a good model. Compare the baseline and inspect the holdout.

# COMMAND ----------
preprocess = ColumnTransformer([
    ("categories", OneHotEncoder(handle_unknown="ignore"), categorical),
    ("numbers", StandardScaler(), numeric),
])
pipeline = Pipeline([("prepare", preprocess),
                     ("classifier", LogisticRegression(max_iter=500, random_state=8))])
with mlflow.start_run(run_name="booking-attendance-logistic") as run:
    mlflow.set_tags({"a8learn_course": COURSE_ID, "a8learn_tag": A8.cfg.tag,
                     "evaluation": "last 10 completed events held out"})
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
    mlflow.log_dict({"features": features, "held_out_events": sorted(held_out),
                     "snapshot": "2026-11-20", "limitations": [
                         "synthetic data", "one temporal holdout", "party attends together",
                         "future bookings not yet made are excluded"]}, "evaluation_contract.json")
    example = train[features].head(5)
    model_info = mlflow.sklearn.log_model(
        pipeline, name="attendance", input_example=example,
        signature=infer_signature(example, pipeline.predict_proba(example)),
        pyfunc_predict_fn="predict_proba",
        pip_requirements=["scikit-learn==1.7.2", "pandas==2.2.3", "numpy==1.26.4"],
    )
print(pd.Series(metrics))
if metrics["holdout_log_loss"] >= baseline_loss:
    print("Model did not beat the baseline on log loss. Investigate; registration below is for learning, not production approval.")
experiment = mlflow.get_experiment_by_name(A8.experiment_path)
A8.links(("Experiment: inspect this run", "experiment", experiment.experiment_id))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** open the experiment. Inspect parameters, metrics, `evaluation_contract.json`, the model signature and example.
# MAGIC In a team, compare challenger runs before promotion. Explain why AUC alone is not a calibrated turnout forecast.
# MAGIC Optional local experiment: change `C` on LogisticRegression, run once more and compare. Preserve the first run.
# MAGIC
# MAGIC ## 4. Register a version, assign an alias (10 minutes)
# MAGIC An experiment run is evidence. A **registered model version** is a governable release artefact.
# MAGIC `Champion` is a mutable alias, not a stage and not proof of quality. Serving should pin a tested version.
# MAGIC The safety check refuses a pre-existing model without this course's ownership tags.

# COMMAND ----------
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
w = WorkspaceClient()
client = MlflowClient()
model_name = f"{A8.cfg.catalog}.{A8.cfg.schema}.{A8.name('attendance_model')}"
try:
    existing = client.get_registered_model(model_name)
except mlflow.exceptions.MlflowException as error:
    if error.error_code != "RESOURCE_DOES_NOT_EXIST":
        raise
    existing = None
if existing is not None:
    if existing.tags.get("a8learn_course") != COURSE_ID or existing.tags.get("a8learn_tag") != A8.cfg.tag:
        raise PermissionError("Existing model is not this course run. Choose another tag.")
    if w.registered_models.get(model_name).owner != A8.cfg.user:
        raise PermissionError("Existing model is not owned by this learner.")
else:
    client.create_registered_model(model_name, tags={"a8learn_course": COURSE_ID, "a8learn_tag": A8.cfg.tag})
version = mlflow.register_model(model_info.model_uri, model_name)
client.set_registered_model_alias(model_name, "Champion", version.version)
A8.links(("Registered model: versions and aliases", "model", "attendance_model"))
print(f"Champion → version {version.version}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Score through the registered model, not the in-memory estimator (15 minutes)
# MAGIC Reloading tests the packaged model. The pyfunc contract returns **[P(no-show), P(attend)]** in classes `[0,1]`.
# MAGIC Here a small table fits in pandas; production batch scoring should distribute work (for example `mlflow.pyfunc.spark_udf`).
# MAGIC The forecast sums tickets × probability for **existing confirmed bookings**.
# MAGIC It does not predict future sales, partial-party attendance or uncertainty intervals.

# COMMAND ----------
released = mlflow.pyfunc.load_model(f"models:/{model_name}@Champion")
scores = np.asarray(released.predict(future[features]))
assert scores.shape == (len(future), 2)
assert np.isfinite(scores).all() and ((scores >= 0) & (scores <= 1)).all()
assert np.allclose(scores.sum(axis=1), 1)
assert np.allclose(scores[:, 1], pipeline.predict_proba(future[features])[:, 1])
scored = future[["booking_id", "event_id", "tickets"]].copy()
scored["attendance_probability"] = scores[:, 1]
scored["model_version"] = str(version.version)
A8.guard("attendance_predictions")
spark.createDataFrame(scored).createOrReplaceTempView("a8_scored_bookings")
A8.run("""CREATE OR REPLACE TABLE {attendance_predictions} USING DELTA
COMMENT 'a8-databricks-learning probabilities for confirmed future bookings'
AS SELECT * FROM a8_scored_bookings""")
A8.guard("event_forecast")
A8.run("""CREATE OR REPLACE VIEW {event_forecast}
COMMENT 'a8-databricks-learning expected turnout from existing bookings only'
AS SELECT e.event_id, e.event_name, e.event_date, e.capacity,
coalesce(sum(p.tickets), 0) AS confirmed_tickets,
coalesce(sum(p.tickets * p.attendance_probability), 0) AS expected_attendees
FROM {events} e LEFT JOIN {attendance_predictions} p USING (event_id)
WHERE e.status = 'scheduled'
GROUP BY e.event_id, e.event_name, e.event_date, e.capacity""")
display(A8.sql("SELECT * FROM {event_forecast} ORDER BY event_date"))
assert A8.sql("SELECT count(*) FROM {event_forecast}").first()[0] == 12
assert A8.sql("""SELECT count(*) FROM {event_forecast}
WHERE expected_attendees < 0 OR expected_attendees > confirmed_tickets""").first()[0] == 0
A8.links(("Forecast: inspect upstream lineage", "table", "event_forecast"))

# COMMAND ----------
answer_3_1 = """"""
A8.check("3.1", answer_3_1)

# COMMAND ----------
# MAGIC %md
# MAGIC **UI exercise:** chart confirmed tickets and expected attendees by event. Which difference might an organiser misinterpret?
# MAGIC Explain to a colleague: "Expected attendance covers only bookings we already have." Which extra model would predict new sales?
# MAGIC
# MAGIC ## 6. Optional: deploy a real-time endpoint
# MAGIC Batch tables cost no continuously provisioned serving endpoint. Online serving adds a REST API and its own permissions.
# MAGIC Set `deploy_serving` to yes **only** if your workspace allows custom model serving and you accept the cost.
# MAGIC This uses the smallest workload and scale-to-zero, but does not guarantee zero cost. Provisioning can take many minutes.
# MAGIC Free Edition availability/quotas differ; a capability error does not invalidate batch inference.
# MAGIC Existing endpoints are never updated here. If this cell is interrupted, open Serving and delete the exact endpoint
# MAGIC below, or run `99_pause_and_cleanup`. Do not keep retrying quota errors.

# COMMAND ----------
if A8.gate("deploy_serving", "Create a billable attendance serving endpoint?"):
    from databricks.sdk.service.serving import (
        EndpointCoreConfigInput, ServedEntityInput, EndpointTag,
    )
    # Create only: a collision fails, never updates an existing endpoint.
    endpoint = w.serving_endpoints.create_and_wait(
        name=A8.endpoint_name,
        config=EndpointCoreConfigInput(served_entities=[
            ServedEntityInput(entity_name=model_name, entity_version=str(version.version),
                              workload_size="Small", scale_to_zero_enabled=True)
        ]),
        tags=[EndpointTag(key="a8learn_course", value=COURSE_ID),
              EndpointTag(key="a8learn_tag", value=A8.cfg.tag)],
    )
    payload = {"dataframe_split": future[features].head(2).to_dict(orient="split")}
    response = w.api_client.do("POST", f"/serving-endpoints/{A8.endpoint_name}/invocations", body=payload)
    online = np.asarray(response["predictions"])
    assert np.allclose(online, scores[:2], atol=1e-6)
    print("Online response matches batch probabilities for the same two bookings.")
    A8.links(("Your endpoint: inspect status/logs, then delete", "endpoint", A8.endpoint_name))
else:
    print("Serving skipped. The registered model and batch forecast are the core outcome.")

# COMMAND ----------
# MAGIC %md
# MAGIC **UI alternative:** Serving → Create endpoint → choose this model/version → Small → scale to zero.
# MAGIC Name it exactly as printed by `A8.endpoint_name`; add the two course tags shown in code before creating.
# MAGIC Query it using the model input example, inspect permissions and logs, then **delete**, not just stop compute.
# MAGIC Serving an sklearn predictor is not a GenAI model call. Next stage adds both, then connects them to an app.
# MAGIC
# MAGIC **Recap:** identify the unit of prediction, the temporal split, the baseline, run ID, model version,
# MAGIC alias and batch output. Which are immutable evidence, and which can move?
# MAGIC **Stop here for Stage 1.** Modules 4–8 are planned, not yet supplied. Remove any serving endpoint now.

# COMMAND ----------
print("Optional endpoint name:", A8.endpoint_name)
A8.next_step(["Booking-time feature table and temporal holdout", "MLflow run with baseline and metrics",
              "UC model version and Champion alias", "Registered-model batch inference and event turnout view"],
             "99_pause_and_cleanup", "Pause safely or remove only your course work")
