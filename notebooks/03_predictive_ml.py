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
# MAGIC **60–75 minutes:** environment 5 · MLflow 5 · features 10 · split and baseline 10 · train 15 · register 10 · score 15 · serving 10 (optional).
# MAGIC
# MAGIC **Before you start:** run Module 1. Module 2 is not needed; its governed copy is deliberately not used for training.
# MAGIC
# MAGIC **What this writes:** a features table, a predictions table, a forecast view, an MLflow experiment,
# MAGIC and a new model version each time you train.
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
# MAGIC %md
# MAGIC ## 1. Connect to MLflow (5 minutes)
# MAGIC **MLflow** keeps the evidence of machine learning work. Two parts matter today:
# MAGIC - **Tracking.** An *experiment* is a folder of *runs*. A run stores the settings, scores and files
# MAGIC   from one training attempt, so you can compare attempts and reproduce the one you chose.
# MAGIC - **Model registry.** A place to publish a trained model as numbered *versions*. Here the registry is
# MAGIC   **Unity Catalog**, so a model is governed like a table: `catalog.schema.model_name`, with permissions and lineage.
# MAGIC
# MAGIC Your experiment lives in your workspace user folder; the printed link opens it.

# COMMAND ----------
# WHAT: checks Module 1's tables exist, then points MLflow at Unity Catalog and at your experiment.
# LOOK FOR: "MLflow 3.6.0" and your experiment path. A PermissionError means another course run uses this tag.
A8.require("events", "bookings")  # stops with a clear message if Module 1 has not been run

import mlflow
from mlflow import MlflowClient
from mlflow.models import infer_signature  # used in section 4 to record the model's input/output contract

# Publish models to Unity Catalog, not the older per-workspace model registry.
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()  # lower-level API, used for tags, aliases and the registry

# Course safety, not an MLflow concept: refuse an experiment at this path that belongs to another
# course run, and restore yours if an earlier cleanup deleted it.
A8.claim_experiment(client)
# Create the experiment the first time, or select it on later runs. Every run below is logged here.
experiment = mlflow.set_experiment(A8.experiment_path)
A8.mark_experiment(client, experiment)  # course tags let cleanup find exactly this experiment
print("MLflow", mlflow.__version__, "| experiment:", experiment.name)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Decide what to predict, then build features (10 minutes)
# MAGIC **The prediction:** will a *confirmed booking* turn up? One row per booking. The **label** (the answer the
# MAGIC model learns) is 1 for attended and 0 for no-show. We are not predicting whether an event sells out.
# MAGIC
# MAGIC **The golden rule:** use only facts known **when the booking was made**. Feedback and attendance are only
# MAGIC known afterwards. Using them would *leak* the answer: the model would score brilliantly in testing and fail in use.
# MAGIC
# MAGIC Two simplifications, because the data is synthetic:
# MAGIC - everyone in one booking attends together
# MAGIC - the data is frozen at 20 November 2026, so scheduled events have an **unknown** label (NULL), not 0
# MAGIC
# MAGIC **Predict before you run:** the query joins bookings to events, and both have a `status`.
# MAGIC Which one is filtered, and why are cancelled bookings left out?

# COMMAND ----------
# WHAT: builds one Delta table of features and label, one row per confirmed booking.
# LOOK FOR: completed events have label 0 or 1; scheduled events have label null (not known yet).
from a8learn import COURSE_ID

A8.guard("booking_features")  # course safety: never replace a table you do not own
A8.run(f"""CREATE OR REPLACE TABLE {{booking_features}} USING DELTA
COMMENT 'a8-databricks-learning booking-time attendance features'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')
AS SELECT b.booking_id, b.event_id,                   -- identifiers: for joining back, not features
b.tickets, b.ticket_type, b.organisation_type,        -- facts about the booking
e.format, e.city, e.start_hour,                       -- facts about the event
dayofweek(e.event_date) AS weekday,
datediff(e.event_date, b.booked_date) AS lead_days,   -- how far ahead the booking was made
e.price_gbp, e.event_date, e.status AS event_status,
CAST(b.attended AS INT) AS label                      -- the answer: 1, 0, or NULL if not yet known
FROM {{bookings}} b JOIN {{events}} e USING (event_id)
WHERE b.status = 'confirmed'                          -- cancelled bookings cannot attend
""")
display(A8.sql("SELECT event_status, label, count(*) AS bookings FROM {booking_features} GROUP BY ALL"))

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
# MAGIC   It is our main measure.
# MAGIC - **AUC** (0.5 is guessing, 1.0 is perfect) asks whether attendees get higher probabilities than no-shows.
# MAGIC - **Accuracy** can look good just by predicting "everyone attends", so never use it alone.
# MAGIC
# MAGIC Do not keep tweaking the model against this one test set; you would slowly fit the test instead of the problem.

# COMMAND ----------
# WHAT: loads the features into pandas, splits by event date, checks the split, then scores the baseline.
# LOOK FOR: three booking counts, and the baseline log loss. The model in section 4 must beat this number.
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.metrics import log_loss

frame = spark.table(A8.t("booking_features")).toPandas()  # small data, so pandas on one machine is fine
categorical = ["ticket_type", "organisation_type", "format", "city"]
numeric = ["tickets", "start_hour", "weekday", "lead_days", "price_gbp"]
features = categorical + numeric  # identifiers, dates and the label are deliberately left out
frame[numeric] = frame[numeric].astype("float64")  # one numeric type for training and the model signature

completed = frame[frame.label.notna()].copy()  # only rows with a known answer can train or test
completed["label"] = completed.label.astype(int)
# Order completed events by date and hold out the last 10: train on the past, test on the "future".
event_order = completed[["event_id", "event_date"]].drop_duplicates().sort_values(["event_date", "event_id"])
held_out = set(event_order.tail(10).event_id)
train = completed[~completed.event_id.isin(held_out)]
test = completed[completed.event_id.isin(held_out)]
future = frame[frame.event_status == "scheduled"].copy()  # no labels yet; scored in section 6

# Guard rails: if any of these fail, the split is wrong, so stop rather than train on it.
assert not set(train.event_id) & set(test.event_id)  # no event on both sides
assert train.event_date.max() <= test.event_date.min()  # training is strictly earlier
assert future.label.isna().all() and len(future) > 0
assert not {"customer_email", "customer_name", "label", "event_id", "event_date"} & set(features)
assert set(train.label) == {0, 1} and set(test.label) == {0, 1}

# "prior" predicts the training attendance rate for every booking and ignores the features.
baseline = DummyClassifier(strategy="prior").fit(train[features], train.label)
baseline_p = baseline.predict_proba(test[features])[:, 1]  # column 1 is P(attend)
baseline_loss = log_loss(test.label, baseline_p)
print(f"Train {len(train)}, holdout {len(test)}, future {len(future)} bookings")
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
# WHAT: builds the preparation + logistic regression pipeline, trains it inside an MLflow run and logs the evidence.
# LOOK FOR: four metrics (compare holdout_log_loss with baseline_log_loss) and a link to your experiment.
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

preprocess = ColumnTransformer([
    # ignore unseen categories at scoring time instead of failing
    ("categories", OneHotEncoder(handle_unknown="ignore"), categorical),
    ("numbers", StandardScaler(), numeric),
])
pipeline = Pipeline([("prepare", preprocess),
                     ("classifier", LogisticRegression(max_iter=500, random_state=8))])
with mlflow.start_run(run_name="booking-attendance-logistic") as run:  # everything below belongs to one run
    mlflow.set_tags({**A8.course_tags, "evaluation": "last 10 completed events held out"})
    mlflow.log_params({"model": "logistic_regression", "seed": 8, "holdout_events": 10,
                       "train_bookings": len(train), "test_bookings": len(test)})
    pipeline.fit(train[features], train.label)  # training happens here
    probabilities = pipeline.predict_proba(test[features])[:, 1]  # P(attend) for each holdout booking
    metrics = {
        "holdout_accuracy": accuracy_score(test.label, probabilities >= 0.5),
        "holdout_auc": roc_auc_score(test.label, probabilities),
        "holdout_log_loss": log_loss(test.label, probabilities),
        "baseline_log_loss": baseline_loss,
    }
    mlflow.log_metrics(metrics)
    # A file recording how the model was judged and what it cannot do. Reviewers read this, not just scores.
    mlflow.log_dict({"features": features, "held_out_events": sorted(held_out),
                     "snapshot": "2026-11-20", "limitations": [
                         "synthetic data", "one temporal holdout", "party attends together",
                         "future bookings not yet made are excluded"]}, "evaluation_contract.json")
    example = train[features].head(5)
    model_info = mlflow.sklearn.log_model(
        pipeline, name="attendance",
        input_example=example,  # sample input shown in the UI and used to test serving
        signature=infer_signature(example, pipeline.predict_proba(example)),  # input/output contract
        pyfunc_predict_fn="predict_proba",  # generic loaders return probabilities, not 0/1 guesses
        pip_requirements=["scikit-learn==1.7.2", "pandas==2.2.3", "numpy==1.26.4"],  # to reload it elsewhere
    )
print(pd.Series(metrics))
if metrics["holdout_log_loss"] >= baseline_loss:
    print("Model did not beat the baseline on log loss. Investigate; registration below is for learning, not production approval.")
A8.links(("Experiment: inspect this run", "experiment", experiment.experiment_id))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** open the experiment, then the run. Find the parameters, the metrics, `evaluation_contract.json`,
# MAGIC and under the model: its signature and input example.
# MAGIC Why is AUC alone not enough to forecast how many people will turn up?
# MAGIC
# MAGIC **Your turn (optional):** add `C=0.1` to `LogisticRegression(...)` above (smaller `C` means a simpler model),
# MAGIC run the cell again and compare the two runs in the experiment's chart view. Both runs are kept.
# MAGIC
# MAGIC ## 5. Register a version and assign an alias (10 minutes)
# MAGIC A run is **evidence**. A **registered model version** is a **release**: a numbered, permission-controlled copy
# MAGIC that other people and jobs can use. Each registration adds a version; old versions are never overwritten.
# MAGIC
# MAGIC An **alias** such as `Champion` is a movable label pointing at one version. Code that loads
# MAGIC `@Champion` gets whichever version the label points to, so you can promote or roll back without changing code.
# MAGIC An alias is not proof of quality; the evidence in the run is.

# COMMAND ----------
# WHAT: publishes the run's model as a new version in Unity Catalog and points Champion at it.
# LOOK FOR: "Champion → version N". N goes up by one each time you train again.
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # Databricks SDK, signed in as you
model_name = A8.model_name  # catalog.schema.a8_<tag>_attendance_model
# Course safety: create the registered model with course tags, or confirm an existing one is yours.
A8.claim_model(client, w)
# Copy the model logged in this run into the registry as the next version.
version = mlflow.register_model(model_info.model_uri, model_name)
client.set_registered_model_alias(model_name, "Champion", version.version)
A8.links(("Registered model: versions and aliases", "model", "attendance_model"))
print(f"Champion → version {version.version}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Score future bookings with the released model (15 minutes)
# MAGIC We now load the model **from the registry**, not the `pipeline` variable in memory. That tests what other
# MAGIC people would actually use. It returns two columns: **[P(no-show), P(attend)]**.
# MAGIC
# MAGIC Then we forecast turnout per event: **sum of tickets × P(attend)** over the confirmed bookings so far.
# MAGIC It does not predict bookings that have not been made yet, and it gives no uncertainty range.
# MAGIC This table is small, so pandas is fine; for large tables you would score in Spark with `mlflow.pyfunc.spark_udf`.
# MAGIC
# MAGIC **Predict before you run:** can an event's expected attendees ever exceed its confirmed tickets? Why not?

# COMMAND ----------
# WHAT: loads Champion from Unity Catalog, scores future bookings, saves them, then builds a per-event forecast view.
# LOOK FOR: one forecast row per scheduled event (12), with expected_attendees below confirmed_tickets.
import numpy as np

released = mlflow.pyfunc.load_model(f"models:/{model_name}@Champion")
scores = np.asarray(released.predict(future[features]))
# Check the released model behaves like the one we trained before writing anything.
assert scores.shape == (len(future), 2)
assert np.isfinite(scores).all() and ((scores >= 0) & (scores <= 1)).all()
assert np.allclose(scores.sum(axis=1), 1)  # the two probabilities add up to 1
assert np.allclose(scores[:, 1], pipeline.predict_proba(future[features])[:, 1])
scored = future[["booking_id", "event_id", "tickets"]].copy()
scored["attendance_probability"] = scores[:, 1]
scored["model_version"] = str(version.version)  # record which release made each prediction
A8.guard("attendance_predictions")
# Hand the pandas result to Spark as a temporary view, then save it as a Delta table.
spark.createDataFrame(scored).createOrReplaceTempView("a8_scored_bookings")
A8.run("""CREATE OR REPLACE TABLE {attendance_predictions} USING DELTA
COMMENT 'a8-databricks-learning probabilities for confirmed future bookings'
AS SELECT * FROM a8_scored_bookings""")
A8.guard("event_forecast")
# LEFT JOIN keeps scheduled events that have no bookings yet; coalesce turns their empty sums into 0.
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
# MAGIC %md
# MAGIC ### Exercise 3.1: write the forecast yourself
# MAGIC Using only `{attendance_predictions}`, return `event_id` and `expected_attendees`
# MAGIC (the sum of tickets × attendance_probability), one row per event, ordered by `event_id`.
# MAGIC Put your SQL between the triple quotes and run the cell. A blank answer shows a hint.

# COMMAND ----------
# WHAT: checks your SQL against the course's answer on your own tables.
# LOOK FOR: a green "correct" card. `A8.solution("3.1")` shows a worked answer if you are stuck.
answer_3_1 = """"""
A8.check("3.1", answer_3_1)

# COMMAND ----------
# MAGIC %md
# MAGIC **UI exercise:** in the forecast output above, add a bar chart of confirmed tickets and expected attendees by event.
# MAGIC Which difference might an organiser misread? Explain: "Expected attendance covers only bookings we already have."
# MAGIC What extra model would you need to predict bookings not yet made?
# MAGIC
# MAGIC ## 7. Optional: deploy a real-time endpoint (10 minutes)
# MAGIC Batch scoring, as above, runs when you choose and needs no endpoint. **Model serving** instead keeps the model
# MAGIC available behind a REST API, so an app can ask for a prediction at any moment. That convenience has a cost.
# MAGIC
# MAGIC Set the `deploy_serving` widget to **yes** only if your workspace allows custom model serving and you accept the cost.
# MAGIC - It uses the smallest size and *scale to zero*, which reduces but does not guarantee zero cost.
# MAGIC - Provisioning can take many minutes. Free Edition quotas differ; a capability error does not affect batch scoring.
# MAGIC - It only creates a new endpoint; it never updates an existing one. If interrupted, delete the endpoint in
# MAGIC   **Serving** or run `99_pause_and_cleanup`. Do not keep retrying quota errors.

# COMMAND ----------
# WHAT: if you opted in, creates an endpoint serving the Champion version, sends two bookings, and compares answers.
# LOOK FOR: "Online response matches batch probabilities", or "Serving skipped" if you left the widget at no.
if A8.gate("deploy_serving", "Create a billable attendance serving endpoint?"):
    from databricks.sdk.service.serving import (
        EndpointCoreConfigInput, ServedEntityInput, EndpointTag,
    )
    # Create only: a name collision fails rather than updating someone else's endpoint.
    endpoint = w.serving_endpoints.create_and_wait(
        name=A8.endpoint_name,
        config=EndpointCoreConfigInput(served_entities=[
            ServedEntityInput(entity_name=model_name, entity_version=str(version.version),  # pin a tested version
                              workload_size="Small", scale_to_zero_enabled=True)
        ]),
        tags=[EndpointTag(key=k, value=v) for k, v in A8.course_tags.items()],
    )
    # The REST request body: two bookings in pandas "split" format (column names plus rows).
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
# MAGIC **UI alternative:** Serving → Create endpoint → choose this model and version → Small → scale to zero.
# MAGIC Use exactly the name printed below, and add the two course tags (`a8learn_course`, `a8learn_tag`).
# MAGIC Query it with the model's input example, look at its permissions and logs, then **delete** it.
# MAGIC Stopping compute is not enough. Serving this scikit-learn model is not a GenAI call; Module 4 adds those.
# MAGIC
# MAGIC ## Recap
# MAGIC Name the unit of prediction, the time-based split, the baseline, the run, the model version, the alias and
# MAGIC the batch output. **Which of these are fixed evidence, and which can move?**
# MAGIC (The run and version are fixed; the alias and the forecast view change when you retrain.)
# MAGIC
# MAGIC **Stop here for Stage 1.** Modules 4–8 are planned, not yet supplied. Remove any serving endpoint now.

# COMMAND ----------
# WHAT: prints your endpoint's name and summarises what you built.
print("Optional endpoint name:", A8.endpoint_name)
A8.next_step(["Booking-time feature table and temporal holdout", "MLflow run with baseline and metrics",
              "UC model version and Champion alias", "Registered-model batch inference and event turnout view"],
             "99_pause_and_cleanup", "Pause safely or remove only your course work")
