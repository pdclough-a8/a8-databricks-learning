# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 15. Release gate and rollback: ship a new agent version safely, and undo it
# MAGIC **Where this sits:** the last operations module. Module 12 registered the agent as version 1 with a `Champion`
# MAGIC alias. Module 14 built a release gate. This module joins them: new versions are tested **before** they take
# MAGIC the alias, the decision is recorded on the version, and a bad release is undone by moving the alias back.
# MAGIC
# MAGIC **Outcome:** log two candidate versions of the agent (one with fresh seat figures, one with last week's), run
# MAGIC the gate on each against the current `Champion`, move the alias **only** for the one that passes, write the gate
# MAGIC result and the evaluation run id on the version as a **release record**, **roll back** and prove the answers
# MAGIC match the original, and optionally send 10% of your Module 12 endpoint's traffic to a candidate (a **canary**).
# MAGIC
# MAGIC **About 60 minutes, an estimate:** orient 10 · baseline 10 · candidates and gate 15 · release record and
# MAGIC rollback 10 · optional canary 10 · exercise and recap 5.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data`, `08b_rag` and `12_deploy_and_govern` (section 4
# MAGIC registers the model this lesson releases). `14_evaluate_and_monitor` is strongly recommended. The canary needs
# MAGIC the endpoint from Module 12 to exist. All data is synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. Reading and scoring in plain Python need no cloud
# MAGIC action. Writing versions and runs, moving the alias, rolling back and the canary are four separate default-no
# MAGIC switches. If a step is blocked, finish the rest and repeat it in your paid workspace.
# MAGIC
# MAGIC **Cost boundary:** this lesson adds **two model versions** to your agent model and **three evaluation runs** to
# MAGIC your Module 14 experiment (or a new one if you skipped Module 14). The scoring rules make no model request. The
# MAGIC optional canary **changes your existing endpoint** (it creates no new one): it adds a second served version for
# MAGIC a few minutes, sends 20 small requests and puts the endpoint back, and the endpoint's compute may be billed
# MAGIC while it updates on a paid workspace. `99_pause_and_cleanup` removes the model with all its versions.
# MAGIC The traffic split was probed live on Free Edition on 24 November 2026 with throwaway models, and the update
# MAGIC took about six minutes; this notebook has not yet been run live: see `docs/validation.md`.
# MAGIC
# MAGIC ## Release in plain English
# MAGIC A **version** of a registered model never changes once it exists. A **release** is a decision about which
# MAGIC version everything should use, and the **alias** `Champion` is how that decision is stored: code that loads
# MAGIC `models:/<name>@Champion` gets whichever version the alias points at. That makes both directions cheap.
# MAGIC Releasing is moving the alias forward. **Rolling back** is moving it back, because the old
# MAGIC version is still there, exactly as it was tested.
# MAGIC
# MAGIC A **release gate** decides whether the alias may move. A **release record** keeps the evidence: tags on the
# MAGIC version saying what the gate decided, why, and which evaluation run proves it. A **canary** shows a new version
# MAGIC to a small share of real requests first, so a fault harms few customers.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Champion** | the alias for the version that is released; the baseline new versions must not be worse than |
# MAGIC | **Candidate** | a new version someone wants to release; it has no alias until it passes |
# MAGIC | **Release record** | tags on a version: gate result, reasons, evaluation run id, rival version |
# MAGIC | **Rollback** | moving `Champion` back to the version it replaced |
# MAGIC | **Canary** | sending a small share of requests to the candidate, here 10%, before everyone gets it |
# MAGIC
# MAGIC **Business question for this lesson:** *when we change the customer assistant, how do we stop a bad version
# MAGIC reaching customers, and how fast can we undo one that got through?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Model versions and aliases in Unity Catalog](https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle/)
# MAGIC - [Serve multiple models on one endpoint](https://docs.databricks.com/aws/en/machine-learning/model-serving/serve-multiple-models-to-serving-endpoint)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------
# MAGIC %md
# MAGIC **Install the MLflow version this lesson was written for.** `%pip install` installs packages **for this
# MAGIC notebook only**. **Expect a red `ERROR: pip's dependency resolver…` message:** the environment also contains
# MAGIC `databricks-agents`, which wants a newer MLflow. This lesson does not use it, so the message is harmless.

# COMMAND ----------
# MAGIC %pip install mlflow==3.6.0 typing_extensions==4.15.0

# COMMAND ----------

# WHAT: restarts this notebook's Python process so the pinned packages are the ones imported.
# LOOK FOR: no output. The next cell will print your catalog, schema and tag.
dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; release holds the alias, rollback and canary rules, evaluation the scoring rules.

import json
import sys
import tempfile
import time
from pathlib import Path

import mlflow
import pandas as pd
from a8learn import release, sql_string
from a8learn import evaluation as ev
from a8learn.lifecycle import endpoint_for_cleanup
from databricks.sdk import WorkspaceClient
from mlflow import MlflowClient
from mlflow.genai.scorers import scorer

# COMMAND ----------

# WHAT: checks the prerequisites, resolves the names and finds the version that is Champion now.
# LOOK FOR: one Ready line naming the model and its Champion version; "none" means Module 12 section 4 is not done.
availability_key = "seats_live" if spark.catalog.tableExists(A8.t("seats_live")) else "event_availability"
A8.require(availability_key, "doc_chunks")
availability = A8.t(availability_key)
spark.sql(f"DECLARE OR REPLACE VARIABLE a8_current_availability STRING DEFAULT {sql_string(availability)}")
chunks_table = A8.t("doc_chunks")
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
w = WorkspaceClient()
MODEL = A8.agent_model_name
CODE = ROOT / "lib" / "a8learn"
try:
    champion = client.get_model_version_by_alias(MODEL, release.ALIAS).version
except Exception as error:  # no model or no alias: the lesson explains and skips what needs it
    champion = None
    print("No Champion found:", type(error).__name__)
print(f"Ready | model: {MODEL} | Champion: {champion or 'none (run Module 12 section 4 first)'} | "
      f"source: {availability} | experiment: {A8.evaluation_experiment_path}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. The evaluation set and the snapshot
# MAGIC The same five tasks as Modules 9, 12 and 14, with the expected facts read from your view. A gate compares
# MAGIC versions on a fixed set, so we do not change it. We also take a **snapshot** of your tables now: the fresh
# MAGIC candidate will answer from it. **I expect:** 32 chunks and 60 seat rows, as in Module 12.
# MAGIC Setup selects retained Module 13 gold (`seats_live`), falling back to Module 1's historical view if absent.
# MAGIC `IDENTIFIER(a8_current_availability)` in the exercise refers to that same selected source.

# COMMAND ----------

# WHAT: takes the snapshot of your tables, as Module 12 did.
# LOOK FOR: the number of chunks and seat rows.
snapshot = {
    "taken_on": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
    "chunks": [{"doc_name": r["doc_name"], "section": r["section"], "content": r["content"]} for r in spark.sql(
        f"SELECT doc_name, section, content FROM {chunks_table} ORDER BY doc_name, section").collect()],
    "seats": [{"event_name": r["event_name"], "city": r["city"], "event_date": str(r["event_date"]),
               "status": r["status"], "available": int(r["available"])} for r in spark.sql(
        f"SELECT event_name, city, event_date, status, available FROM {availability}").collect()],
}
print(f"{len(snapshot['chunks'])} chunks, {len(snapshot['seats'])} seat rows, taken {snapshot['taken_on']}")

# COMMAND ----------

# WHAT: defines the five tasks and builds the evaluation rows with their expected facts.
# LOOK FOR: five rows; each carries the question under inputs and the expected tool and fact under expectations.
def seats(event_name):
    return int(spark.sql(f"SELECT available FROM {availability} WHERE event_name = :n AND status = 'scheduled'",
                         args={"n": event_name}).collect()[0]["available"])


TASKS = [
    {"task": "How many seats are left for Pipelines in Practice?", "tool": "check_availability",
     "fact": str(seats("Pipelines in Practice"))},
    {"task": "Is there space at the Analytics Breakfast?", "tool": "check_availability",
     "fact": str(seats("Analytics Breakfast"))},
    {"task": "A colleague wants to take over my seat.", "tool": "search_docs", "fact": "booking-and-transfers.md"},
    {"task": "Do I get my money back if I pull out ten days before?", "tool": "search_docs",
     "fact": "cancellations-and-refunds.md"},
    {"task": "What is the weather forecast for the London event?", "tool": None, "fact": None},
]
EVAL_DATA = [{"inputs": {"question": t["task"]}, "expectations": ev.make_expectations(t["tool"], t["fact"])}
             for t in TASKS]
QUESTIONS = pd.DataFrame({"question": [t["task"] for t in TASKS]})
for row in EVAL_DATA:
    print(row["inputs"]["question"], "->", row["expectations"])

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. The scorers and the helpers
# MAGIC The scorers are Module 14's three rules (`right_tool`, `grounded`, `finished`), wrapped for MLflow. The new
# MAGIC part is that the agent under test is **a registered version loaded by number**, as a consumer would load it,
# MAGIC and not the Python code. `evaluate_agent` loads a version, runs the five questions through
# MAGIC `mlflow.genai.evaluate`, tags the run with the version it tested, and returns the marks.
# MAGIC
# MAGIC A loaded model runs its own copy of the agent code, so its individual tool calls are not traced here (Module 14
# MAGIC showed that). The marks, and a trace per answer, are all the gate needs.

# COMMAND ----------

# WHAT: defines the scorers, the evaluation helper and the function that logs and registers a candidate version.
# LOOK FOR: no output; nothing is written until you approve the next section.
@scorer
def right_tool(outputs, expectations):
    return ev.right_tool(outputs, expectations)


@scorer
def grounded(outputs, expectations):
    return ev.grounded(outputs, expectations)


@scorer
def finished(outputs):
    return ev.finished(outputs)


SCORERS = [right_tool, grounded, finished]


def means(result):
    return {k: float(v) for k, v in result.metrics.items() if k.endswith("/mean")}


def evaluate_version(version, label):
    """Load one registered version, evaluate it, tag the run with the version and return (marks, run id)."""
    model = mlflow.pyfunc.load_model(f"models:/{MODEL}/{version}")
    result = mlflow.genai.evaluate(data=EVAL_DATA, predict_fn=release.predict_with_model(model), scorers=SCORERS)
    for key, value in {**A8.course_tags, "mlflow.runName": f"release-{label}", "kind": "release-evaluation",
                       "model_version": str(version)}.items():
        client.set_tag(result.run_id, key, value)
    return means(result), result.run_id


def log_candidate(snap, label):
    """Log the agent with this snapshot and register it as a new version. It has no alias: it is only a candidate."""
    path = Path(tempfile.mkdtemp()) / "snapshot.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    with mlflow.start_run(run_name=f"release-candidate-{label}"):
        mlflow.set_tags({**A8.course_tags, "kind": "agent-candidate", "snapshot_taken_on": snap["taken_on"]})
        info = mlflow.pyfunc.log_model(
            name="agent", python_model=str(CODE / "agent_model.py"), code_paths=[str(CODE / "agent_core.py")],
            artifacts={"snapshot": str(path)}, input_example=QUESTIONS.head(1))
    return mlflow.register_model(info.model_uri, MODEL).version

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Baseline: mark the Champion
# MAGIC First we mark the version that is released now, loading `models:/<name>@Champion` and running the five
# MAGIC questions. We also keep its **five answers**: after a rollback we must be able to prove the same answers come
# MAGIC back. This writes to MLflow (one experiment, one run), after checking the experiment is yours.
# MAGIC
# MAGIC **A gate only compares.** If the Champion's own seat figures were already out of date, a candidate that is
# MAGIC equally out of date would tie with it and pass. Read the baseline's `grounded` mark before you trust the gate.
# MAGIC
# MAGIC **If it differs:** a permission error naming your experiment means another course run uses your tag.
# MAGIC **Undo:** `99_pause_and_cleanup` removes the model and, when you also choose to remove data objects, the
# MAGIC experiment.

# COMMAND ----------

# WHAT: asks for your approval before writing candidate versions and evaluation runs.
# LOOK FOR: a log_candidates widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
candidates_approved = A8.gate("log_candidates", "Write evaluation runs and two new model versions (no alias change)?")
print("Approved." if candidates_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: marks the Champion and keeps its answers.
# LOOK FOR: three means; grounded of 0.8 is normal (one task is deliberately hard); finished must be 1.0.
baseline = baseline_answers = None
if candidates_approved and champion is None:
    print("There is no Champion to compare with. Register the agent in Module 12 section 4 first.")
elif candidates_approved:
    A8.claim_experiment(client, A8.evaluation_experiment_path)
    experiment = mlflow.set_experiment(A8.evaluation_experiment_path)
    A8.mark_experiment(client, experiment)
    A8.claim_model(client, w, MODEL)
    baseline, baseline_run = evaluate_version(champion, "baseline")
    baseline_answers = list(mlflow.pyfunc.load_model(f"models:/{MODEL}@{release.ALIAS}").predict(QUESTIONS)["answer"])
    print(f"Champion is version {champion}:", baseline)
    A8.links(("Your evaluation experiment: runs and traces", "experiment", experiment.experiment_id))
else:
    print("Skipped. The plain-Python parts above are the core outcome; the versions and runs need this step.")

# COMMAND ----------

# WHAT: Check: the Champion finished every task and its answers were kept.
# LOOK FOR: two pass messages.
if baseline is not None:
    A8.expect(baseline.get("finished/mean") == 1.0, "The Champion finished every task.")
    A8.expect(len(baseline_answers) == len(TASKS), "The Champion's five answers were kept for the rollback check.")
else:
    print("Skipped: no baseline.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Two candidates
# MAGIC We log two new versions of the same agent code. **Fresh** answers from a snapshot taken a moment ago.
# MAGIC **Stale** answers from the same snapshot with every seat count out by seven, as if it had been taken last
# MAGIC week. Both are fluent. Neither has an alias, so nothing that loads `@Champion` can see them yet.
# MAGIC
# MAGIC Each version is evaluated by loading it **by number**. **Predict:** which candidate will the gate pass, and
# MAGIC which scorer will fail the other?

# COMMAND ----------

# WHAT: logs and registers the fresh and stale candidates, evaluates both and applies the gate to the fresh one.
# LOOK FOR: two new version numbers, each candidate's marks, and a RELEASE verdict for the fresh candidate.
good_version = bad_version = good_means = bad_means = good_verdict = None
if baseline is not None:
    sys.path.insert(0, str(CODE))  # MLflow runs agent_model.py once while logging, and it imports agent_core
    good_version = log_candidate(snapshot, "fresh")
    bad_version = log_candidate(ev.stale_snapshot(snapshot), "stale")
    good_means, good_run = evaluate_version(good_version, "candidate-fresh")
    bad_means, bad_run = evaluate_version(bad_version, "candidate-stale")
    good_verdict = ev.release_gate(baseline, good_means)
    print(f"Fresh candidate is version {good_version}:", good_means)
    print(f"Stale candidate is version {bad_version}:", bad_means)
    print("Gate for the fresh candidate:", "RELEASE" if good_verdict["passed"] else "BLOCKED", good_verdict["reasons"])
    A8.links(("Your registered agent model: versions and aliases", "model", "agent_model"))
else:
    print("Skipped: no baseline.")

# COMMAND ----------

# WHAT: Check: the versions exist, the stale one is worse only on grounded, and the Champion has not moved.
# LOOK FOR: three pass messages.
if good_version is not None:
    A8.expect(bad_means["finished/mean"] == 1.0 and bad_means["grounded/mean"] < good_means["grounded/mean"],
              "The stale candidate finished every task but is less grounded than the fresh one.")
    A8.expect(good_verdict["passed"], "The fresh candidate passes the gate against the Champion.")
    A8.expect(client.get_model_version_by_alias(MODEL, release.ALIAS).version == champion,
              "Nothing has been released yet: Champion is still the same version.")
else:
    print("Skipped: no candidates.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Release one, refuse the other
# MAGIC Releasing moves the alias, so consumers that **load `@Champion` again** get the new version. Already-loaded
# MAGIC models and the numeric-version-pinned Module 12 endpoint do not change. The alias move has its own switch. For
# MAGIC each candidate we first write its **release record** (gate result, reasons, evaluation run id and the version
# MAGIC it was compared with), then move the alias only if the gate passed.
# MAGIC
# MAGIC Order matters. We release the fresh candidate first, then judge the stale one against the **new** Champion.
# MAGIC That is the careful order: a candidate must beat what is actually running.
# MAGIC
# MAGIC **Undo:** the next section rolls back.

# COMMAND ----------

# WHAT: asks for your approval before moving the Champion alias.
# LOOK FOR: a release_candidate widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
release_approved = A8.gate("release_candidate", "Move the Champion alias to a candidate that passes the gate?")
print("Approved." if release_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: records both decisions and moves Champion only for the candidate that passed.
# LOOK FOR: the fresh version released; the stale version blocked on grounded, with its reasons.
bad_verdict = None
if release_approved and good_version is not None:
    moved = release.record_and_release(client, MODEL, good_version, good_verdict, good_run, champion)
    bad_verdict = ev.release_gate(good_means, bad_means)  # the new Champion's marks are now the baseline
    refused = release.record_and_release(client, MODEL, bad_version, bad_verdict, bad_run, good_version)
    print(f"Version {good_version}: {'released, Champion moved' if moved else 'not released'}")
    print(f"Version {bad_version}: {'released' if refused else 'blocked'}", bad_verdict["reasons"])
elif release_approved:
    print("Skipped: log the candidates first (section 4).")
else:
    print("Skipped: the alias was not moved.")

# COMMAND ----------

# WHAT: Check: Champion is the fresh version, and the blocked version never held the alias.
# LOOK FOR: three pass messages.
if bad_verdict is not None:
    A8.expect(client.get_model_version_by_alias(MODEL, release.ALIAS).version == good_version,
              "Champion now points at the version that passed the gate.")
    A8.expect(not bad_verdict["passed"], "The stale version was blocked by the gate.")
    A8.expect(client.get_model_version(MODEL, bad_version).tags.get("gate") == "blocked",
              "The blocked version carries its release record.")
else:
    print("Skipped: nothing was released.")

# COMMAND ----------

# WHAT: prints the release record kept on each candidate version.
# LOOK FOR: gate, gate_reasons, evaluation_run_id and compared_with_version; the fresh version also has replaces.
if bad_verdict is not None:
    for version in (good_version, bad_version):
        tags = client.get_model_version(MODEL, version).tags
        print(version, {k: tags[k] for k in ("gate", "gate_reasons", "evaluation_run_id", "compared_with_version",
                                             "replaces", "withdrawn") if k in tags})
else:
    print("Skipped: no release record.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Roll back
# MAGIC Suppose the released version turns out to be a problem after all. Rolling back is moving `Champion` to the
# MAGIC version it replaced, which the release record names in the `replaces` tag. Nothing is deleted or rebuilt.
# MAGIC
# MAGIC **Predict:** after the rollback, will `@Champion` give exactly the five answers it gave in section 3? We check.

# COMMAND ----------

# WHAT: asks for your approval before moving the Champion alias back.
# LOOK FOR: a roll_back widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
rollback_approved = A8.gate("roll_back", "Move Champion back to the version it replaced?")
print("Approved." if rollback_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: rolls back and loads Champion again to compare its answers with section 3.
# LOOK FOR: the restored version number and one pass message; the withdrawn version is tagged withdrawn.
restored = None
if rollback_approved and bad_verdict is not None:
    restored = release.roll_back(client, MODEL)
    after = list(mlflow.pyfunc.load_model(f"models:/{MODEL}@{release.ALIAS}").predict(QUESTIONS)["answer"])
    print(f"Champion is version {restored} again; version {good_version} is tagged withdrawn.")
    A8.expect(restored == str(champion) and after == baseline_answers,
              "After the rollback Champion gives exactly the answers it gave before the release.")
elif rollback_approved:
    print("Skipped: nothing was released, so there is nothing to roll back.")
else:
    print("Skipped: Champion was not moved back.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Optional: a canary on your endpoint
# MAGIC An endpoint deployment is separate from moving a registry alias. A **canary** gives the candidate a small
# MAGIC share of real requests first. On **Model Serving** one endpoint can serve several versions and split traffic.
# MAGIC If your Module 12 endpoint exists, we change it to serve the running version at 90% and the fresh
# MAGIC candidate at 10%, send 20 requests, and **always** put it back to the running version, even if a request fails.
# MAGIC
# MAGIC **What you can and cannot see.** Versions may answer differently if their snapshots differ, but a reply does
# MAGIC not identify which version produced it. We show the split by reading the endpoint's traffic routes back,
# MAGIC and that all 20 requests were answered. The update waits for the endpoint to be ready, which took about six
# MAGIC minutes on Free Edition. **This lesson does not create an endpoint:** if yours is absent it says so and
# MAGIC moves on.
# MAGIC
# MAGIC **If it differs:** a message that the update is not allowed means your workspace cannot split traffic; the
# MAGIC rest of the lesson stands. If the restore fails, run `99_pause_and_cleanup` or delete the endpoint in Module 12.

# COMMAND ----------

# WHAT: asks for your approval before changing your existing endpoint.
# LOOK FOR: a canary_endpoint widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
canary_approved = A8.gate("canary_endpoint", "Split your agent endpoint 90/10 for a few minutes, then restore it?")
print("Approved." if canary_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: defines the helpers that read the endpoint and wait for an update to finish.
# LOOK FOR: no output.
ENDPOINT_URL = f"/api/2.0/serving-endpoints/{A8.agent_endpoint_name}"


def wait_for_endpoint(minutes=20):
    """Poll the endpoint until no update is running and it is ready; return the last reply."""
    for _ in range(minutes * 4):
        reply = w.api_client.do("GET", ENDPOINT_URL)
        state = reply.get("state", {})
        if state.get("config_update") == "NOT_UPDATING" and state.get("ready") == "READY":
            return reply
        time.sleep(15)
    raise TimeoutError("The endpoint did not become ready in time; check Serving in the UI.")

# COMMAND ----------

# WHAT: splits the endpoint 90/10, sends 20 requests, then restores it in a finally block.
# LOOK FOR: routes of 90 and 10 while split, 20 answers, then one route of 100 after the restore.
canary_split = canary_restored = canary_answers = None
if canary_approved and good_version is None:
    print("Skipped: log the candidates first (section 4).")
elif canary_approved:
    if endpoint_for_cleanup(A8, w, A8.agent_endpoint_name) is None:
        print("There is no agent endpoint of yours to split. Serve one in Module 12 first.")
    else:
        entities = w.api_client.do("GET", ENDPOINT_URL)["config"]["served_entities"]
        if len(entities) != 1 or entities[0]["entity_name"] != MODEL:
            print("The endpoint does not serve a single version of your agent model; it was not changed.")
        else:
            running = entities[0]
            split, restore = release.canary_bodies(MODEL, running["name"], running["entity_version"], good_version)
            try:
                w.api_client.do("PUT", f"{ENDPOINT_URL}/config", body=split)
                canary_split = release.routes(wait_for_endpoint())
                canary_answers = [w.api_client.do(
                    "POST", f"/serving-endpoints/{A8.agent_endpoint_name}/invocations",
                    body={"dataframe_records": [{"question": TASKS[0]["task"]}]})["predictions"][0]["answer"]
                    for _ in range(20)]
            finally:
                w.api_client.do("PUT", f"{ENDPOINT_URL}/config", body=restore)
                canary_restored = release.routes(wait_for_endpoint())
            print("While split:", canary_split, "| answers:", len(canary_answers), "| after restore:", canary_restored)
else:
    print("Skipped: your endpoint was not changed.")

# COMMAND ----------

# WHAT: Check: the split was 90/10, every request was answered, and the endpoint was put back.
# LOOK FOR: three pass messages.
if canary_split is not None:
    A8.expect(sorted(canary_split.values()) == [10, 90], "The endpoint split traffic 90/10 between two versions.")
    A8.expect(len(canary_answers) == 20 and all(canary_answers), "All 20 requests were answered.")
    A8.expect(list(canary_restored.values()) == [100], "The endpoint is back to one version at 100%.")
else:
    print("Skipped: no canary was run.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Your turn
# MAGIC The stale candidate would have told customers wrong seat counts. The first exercise reproduces what it would
# MAGIC say; the second asks you to decide which version takes the alias:
# MAGIC 1. Exercise 15.1: the true and the stale seat count for the two seat questions, as a table.
# MAGIC 2. Exercise 15.2, a decision: write `choose_champion`, the rule for which version should hold `Champion`. It is
# MAGIC    run against six supplied situations (no cloud calls), and a wrong decision is explained case by case.
# MAGIC
# MAGIC Use `IDENTIFIER(a8_current_availability)` for the selected source. A blank answer shows the task and a hint.
# MAGIC `A8.solution("15.1")` or `A8.solution("15.2")` shows a worked answer. You can also answer 15.1 with a Spark or
# MAGIC pandas DataFrame.

# COMMAND ----------

# WHAT: Check: compares your exercise 15.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_15_1 = """"""
A8.check("15.1", answer_15_1)

# COMMAND ----------

# WHAT: Check: runs your release rule against six supplied situations.
# LOOK FOR: the task while the body is `...`; otherwise "correct on all 6 cases" or the first case it decides wrongly.
def choose_champion(current, candidates):
    ...  # your rule here: return the version number that should hold Champion


A8.check_rule("15.2", choose_champion)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: which tag would you want on a version if you were
# MAGIC woken at night to decide whether to roll it back?
# MAGIC
# MAGIC **Completion requires:** the exercises, the checks above, your explanations and, if you approved them, the
# MAGIC candidate versions, the release and the rollback. The canary is optional. Being blocked on a cloud step is
# MAGIC fine: record it, and do not count that outcome as complete.
# MAGIC
# MAGIC **Pause:** this lesson added two versions to your agent model and three runs to your experiment. They cost
# MAGIC nothing to keep; `99_pause_and_cleanup` removes them. If you ran the canary, check that the endpoint shows one
# MAGIC version, and delete the endpoint (Module 12 section 9) when you have finished with it.
# MAGIC **Next:** `99_pause_and_cleanup`.

# COMMAND ----------
# WHAT: asks why the evaluation run id and gate result are kept on the version.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_15_a = """"""
A8.reflect("15.a", my_answer_15_a)

# COMMAND ----------
# WHAT: asks why a rollback moves an alias and does not edit or delete a version.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_15_b = """"""
A8.reflect("15.b", my_answer_15_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["Candidate versions tested by number before they hold the Champion alias",
              "A release record of the gate result and evaluation run on every version",
              "One candidate released, a stale one refused, and a rollback proved by identical answers",
              "An optional 90/10 canary on a serving endpoint"],
             "99_pause_and_cleanup", "Pause safely or remove only your course work")
