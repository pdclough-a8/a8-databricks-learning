# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 12. Deploy and govern: from a notebook agent to a registered, served model
# MAGIC **Where this sits:** the operations end of the course. Module 9 built an agent that lives in a notebook. A
# MAGIC notebook agent is not something other people or other systems can use, and nobody can say which version is
# MAGIC running. This module turns it into a **model**: packaged, recorded, versioned, labelled, served and
# MAGIC controlled.
# MAGIC
# MAGIC **Outcome:** package the Module 9 agent as plain code with a frozen **snapshot** of its data, test it
# MAGIC locally, **log** it with MLflow, **register** it in Unity Catalog with a `Champion` alias, **serve** it on a
# MAGIC REST endpoint, query the endpoint, check the endpoint's answers against the local ones, look at who can
# MAGIC use it, and **remove** it.
# MAGIC
# MAGIC **About 90 minutes, an estimate:** orient 10 · package and test 20 · log and register 20 · serve and query
# MAGIC 20 (mostly waiting) · govern 10 · exercises and recap 10.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data` and `08b_rag` (the chunk table). `09_agents` is
# MAGIC recommended. All data is synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. Packaging and local testing need no cloud action.
# MAGIC Logging, registering and serving each sit behind a default-no switch. If any step is blocked, finish the rest
# MAGIC and repeat that step in your paid workspace after running `00_setup`, `01_lakehouse_data` and `08b_rag` there.
# MAGIC
# MAGIC **Cost boundary:** this lesson creates **one MLflow run, one Unity Catalog model and one serving endpoint**.
# MAGIC The endpoint uses the smallest size and scales to zero, but it can take about five minutes to become ready
# MAGIC and **can bill while it exists**. Delete it in the last section, or with `99_pause_and_cleanup`. This lesson
# MAGIC was validated live on Free Edition on 24 November 2026.
# MAGIC
# MAGIC ## Deployment in plain English
# MAGIC A recipe in your own notebook is not a restaurant. To serve customers you need the recipe written down
# MAGIC (**packaging**), a record of which version of it is in use (**registry**), a kitchen that is open when asked
# MAGIC (**serving**) and rules about who may order and who may change it (**governance**). Each step has a Databricks
# MAGIC feature: MLflow records what was built, Unity Catalog holds versions and permissions, and Model Serving
# MAGIC runs it behind a URL.
# MAGIC
# MAGIC **One honest limit.** The agent served here answers from a **snapshot**: a copy of the knowledge-base chunks
# MAGIC and seat numbers taken when the model is logged, saved inside the model. That keeps the deployed model
# MAGIC self-contained and easy to verify, but its seat numbers go **stale** as bookings change. It also uses the
# MAGIC rule-based decider from Module 9, because a served model can only call another model or a table after extra
# MAGIC authentication is set up, which this course does not attempt on Free Edition. Both limits are discussed in
# MAGIC the recap.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Packaging** | putting code and the data it needs into one self-contained unit |
# MAGIC | **Snapshot** | a copy of the data taken at one moment and stored inside the model |
# MAGIC | **MLflow run** | the recorded evidence of one build: parameters, files, the logged model |
# MAGIC | **Signature** | the model's declared input and output columns |
# MAGIC | **Registered model** | a named model in Unity Catalog with numbered versions and permissions |
# MAGIC | **Version / alias** | one numbered release / a movable label such as `Champion` pointing at a version |
# MAGIC | **Serving endpoint** | the model behind a REST URL that anything with permission can call |
# MAGIC | **Scale to zero** | the endpoint shuts compute down when idle, so the first call after a pause is slow |
# MAGIC | **Governance** | who may query, change or delete the model and the endpoint, and how that is recorded |
# MAGIC
# MAGIC **Business question for this lesson:** *can the customer assistant be offered to other systems as a versioned
# MAGIC service, and how do we know exactly what is running and who may use it?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Log and register models in Unity Catalog](https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle/)
# MAGIC - [Model Serving](https://docs.databricks.com/aws/en/machine-learning/model-serving/)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------
# MAGIC %md
# MAGIC **Install the MLflow version this lesson was written for.** `%pip install` installs packages **for this
# MAGIC notebook only**. Logging a model changed its call between MLflow versions, so we pin one. **Expect a red
# MAGIC `ERROR: pip's dependency resolver…` message:** the environment also contains `databricks-agents`, which wants a
# MAGIC newer MLflow. This lesson does not use it, so the message is harmless.

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
# LOOK FOR: no output; json and tempfile handle the snapshot file, mlflow does the logging and registering.
import json
import re
import sys
import tempfile
from pathlib import Path

import mlflow
import pandas as pd
from a8learn import agent_core
from a8learn.lifecycle import endpoint_for_cleanup
from databricks.sdk import WorkspaceClient
from mlflow import MlflowClient

# COMMAND ----------

# WHAT: checks the prerequisites and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming the source tables, your model name and your endpoint name.
A8.require("event_availability", "doc_chunks")
availability = A8.t("event_availability")
chunks_table = A8.t("doc_chunks")
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
w = WorkspaceClient()
print(f"Ready | {availability} | {chunks_table} | model: {A8.agent_model_name} | endpoint: {A8.agent_endpoint_name}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Package the agent
# MAGIC The agent from Module 9 used notebook variables and Spark. A served model has neither, so it is rewritten as two
# MAGIC small Python files in `lib/a8learn`:
# MAGIC - `agent_core.py`: the same tools, guardrails, loop and rule-based decider, with no Spark and no network. It
# MAGIC   reads everything from a **snapshot** dictionary.
# MAGIC - `agent_model.py`: a thin MLflow wrapper. It loads the snapshot when the model starts and answers a table of
# MAGIC   questions, one row each.
# MAGIC
# MAGIC Read the code before you log it. **Predict:** which of the Module 9 safety rules (allow-list, input checks,
# MAGIC step cap, trace) can you find, and which one is missing because nothing is logged on the way?

# COMMAND ----------

# WHAT: prints the packaged agent code that will be stored inside the model.
# LOOK FOR: the allow-list TOOLS, run_tool's input checks, the MAX_STEPS cap and the snapshot lookups.
CODE = ROOT / "lib" / "a8learn"
print((CODE / "agent_core.py").read_text(encoding="utf-8"))

# COMMAND ----------

# WHAT: prints the MLflow wrapper that loads the snapshot and answers a table of questions.
# LOOK FOR: load_context reading the snapshot, predict returning answer, status and steps, and set_model at the end.
print((CODE / "agent_model.py").read_text(encoding="utf-8"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Take the snapshot
# MAGIC The snapshot is the data the deployed agent will know: every knowledge-base chunk and the seat numbers for
# MAGIC every event. We read them from your tables once, and write them to a small file that becomes part of the model.
# MAGIC The file is written to a temporary folder, not to your catalog.
# MAGIC
# MAGIC **I expect:** 32 chunks and 60 events. **If it differs:** fewer chunks means `08b_rag` has not finished here.

# COMMAND ----------

# WHAT: reads the chunks and the seat numbers from your tables into a snapshot dictionary.
# LOOK FOR: the number of chunks and seat rows, and the date of the snapshot.
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

# WHAT: writes the snapshot to a temporary file and checks it reads back unchanged.
# LOOK FOR: one pass message; this is the file MLflow will store inside the model.
snapshot_path = Path(tempfile.mkdtemp()) / "snapshot.json"
snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
A8.expect(json.loads(snapshot_path.read_text(encoding="utf-8")) == snapshot, "The snapshot file reads back unchanged.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Test before you release
# MAGIC Never register what you have not tested. We run the same five tasks as Module 9 through the packaged code
# MAGIC and score them: tool choice, and whether the answer carries the real seat number or names the right document.
# MAGIC The seat numbers are read straight from your view, so the agent cannot mark its own work.
# MAGIC
# MAGIC **Predict:** Module 9's rule-based agent got four of five grounded. Will the packaged copy match?

# COMMAND ----------

# WHAT: defines the five tasks with their expected tool and independently read facts.
# LOOK FOR: no output; seats come from the view, not from the agent.
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


def grounded(answer_text, task):
    if task["tool"] is None:  # nothing can answer it: the answer must be a refusal, not a guess
        return bool(re.search(r"can't|cannot|not find|don't|no information", answer_text.lower()))
    return task["fact"] in answer_text

# COMMAND ----------

# WHAT: runs the packaged agent on the five tasks and scores it.
# LOOK FOR: one line per task with its steps and a grounded flag, then the total.
local = [agent_core.answer(snapshot, t["task"]) for t in TASKS]
flags = [grounded(result["answer"], task) for result, task in zip(local, TASKS, strict=True)]
for result, task, flag in zip(local, TASKS, flags, strict=True):
    print(f"{'ok ' if flag else 'MISS'} {task['task']} | steps {result['steps']} | {result['status']}")
print(f"Grounded {sum(flags)}/{len(TASKS)}")

# COMMAND ----------

# WHAT: Check: the packaged agent finished every task and matches the Module 9 baseline.
# LOOK FOR: two pass messages; four of five grounded is the baseline, so this is a release gate, not a high mark.
A8.expect(all(r["status"] == "answered" for r in local), "Every task ended with an answer inside the step cap.")
A8.expect(sum(flags) >= 4, "The packaged agent is at least as good as the Module 9 rule-based baseline (4 of 5).")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Log and register the model
# MAGIC Two steps, two records. **Logging** stores the model, its code, its snapshot and its **signature** (the
# MAGIC input and output columns, taken from an example) in an MLflow run: the evidence of what was built.
# MAGIC **Registering** copies it into Unity Catalog as **version 1** of your model, where it has an owner,
# MAGIC permissions and history. We then point the alias `Champion` at that version. Anything that loads
# MAGIC `models:/<name>@Champion` gets the released version, and moving the alias is how you roll forward or back.
# MAGIC
# MAGIC Before writing we check the name is not someone else's: a model that is not yours stops the lesson.
# MAGIC Every run, model and endpoint carries your course tags so cleanup removes only yours.
# MAGIC
# MAGIC **If it differs:** a permission error on the catalog means you cannot create models here; use your paid
# MAGIC workspace. A `PermissionError` naming your model means another course run uses your tag. **Undo:** the model
# MAGIC and its versions are removed by `99_pause_and_cleanup`; MLflow runs are kept as evidence.

# COMMAND ----------

# WHAT: asks for your approval before anything is written to MLflow or Unity Catalog.
# LOOK FOR: a register_agent widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
register_approved = A8.gate("register_agent", "Log the agent to MLflow and register it in Unity Catalog?")
print("Approved." if register_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: logs the agent, registers it as a new version and points the Champion alias at it.
# LOOK FOR: the registered name and version number; a rerun adds a new version, it never edits an old one.
version = None
if register_approved:
    sys.path.insert(0, str(CODE))  # MLflow runs agent_model.py once while logging, and it imports agent_core
    A8.claim_experiment(client)
    experiment = mlflow.set_experiment(A8.experiment_path)
    A8.mark_experiment(client, experiment)
    A8.claim_model(client, w, A8.agent_model_name)
    with mlflow.start_run(run_name="support-agent-snapshot") as run:
        mlflow.set_tags({**A8.course_tags, "kind": "agent", "snapshot_taken_on": snapshot["taken_on"]})
        mlflow.log_params({"decider": "rules", "max_steps": agent_core.MAX_STEPS, "chunks": len(snapshot["chunks"]),
                           "seat_rows": len(snapshot["seats"])})
        mlflow.log_metric("grounded_tasks", sum(flags))
        model_info = mlflow.pyfunc.log_model(
            name="agent", python_model=str(CODE / "agent_model.py"), code_paths=[str(CODE / "agent_core.py")],
            artifacts={"snapshot": str(snapshot_path)},
            input_example=pd.DataFrame({"question": [TASKS[0]["task"]]}))
    version = mlflow.register_model(model_info.model_uri, A8.agent_model_name)
    client.set_registered_model_alias(A8.agent_model_name, "Champion", version.version)
    print(f"Registered {A8.agent_model_name} version {version.version}, alias Champion.")
    A8.links(("Your registered agent model: versions and aliases", "model", "agent_model"))
else:
    print("Skipped. Packaging and local testing above are the core outcome; the rest needs this step.")

# COMMAND ----------

# WHAT: describes the model for the people who find it in the catalog, and records what it was built from.
# LOOK FOR: no output; the description and version tags appear on the model page.
if version is not None:
    client.update_registered_model(
        A8.agent_model_name, description="A8 Events support agent (rule-based decider) answering from a snapshot of "
                                         "knowledge-base chunks and seat numbers. Synthetic course data.")
    client.set_model_version_tag(A8.agent_model_name, version.version, "snapshot_taken_on", snapshot["taken_on"])
    client.set_model_version_tag(A8.agent_model_name, version.version, "tested_grounded", f"{sum(flags)}/{len(TASKS)}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Load the released version and compare
# MAGIC The point of an alias is that other code loads it by name. We load `Champion` back from Unity Catalog, as a
# MAGIC consumer would, and send it the same five questions. If the registered model is the model we tested, the
# MAGIC answers are identical to the local ones.

# COMMAND ----------

# WHAT: loads the Champion version from Unity Catalog and answers the five questions with it.
# LOOK FOR: one pass message; the loaded model must give exactly the answers the local code gave.
loaded_answers = None
if version is not None:
    released = mlflow.pyfunc.load_model(f"models:/{A8.agent_model_name}@Champion")
    loaded_answers = released.predict(pd.DataFrame({"question": [t["task"] for t in TASKS]}))
    A8.expect(list(loaded_answers["answer"]) == [r["answer"] for r in local],
              "The released model answers exactly as the code you tested.")
    print("Signature:", released.metadata.signature)
else:
    print("Skipped: no registered version to load.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Serve it
# MAGIC **Model Serving** runs the registered version on managed compute behind a REST URL. We create the endpoint
# MAGIC pinned to **the version we just registered**, not to the alias, so the running version never changes without
# MAGIC a decision. The endpoint is tagged as yours. If one with your name already exists and is yours, we leave it
# MAGIC alone; if it is not yours, the lesson stops.
# MAGIC
# MAGIC Set `deploy_agent` to **yes** only if you accept the cost. Creating the endpoint waits until it is ready,
# MAGIC about five minutes. Do not retry in a loop if it fails; read the message, then check **Serving** in the UI.
# MAGIC
# MAGIC **If it differs:** a message about quota or unsupported features means your workspace cannot serve custom
# MAGIC models; finish the rest and repeat this step in your paid workspace. **Undo:** the last section, or
# MAGIC `99_pause_and_cleanup`.

# COMMAND ----------

# WHAT: asks for your approval before creating a billable endpoint.
# LOOK FOR: a deploy_agent widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
deploy_approved = A8.gate("deploy_agent", "Create a billable serving endpoint for the agent?")
print("Approved." if deploy_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: creates your endpoint for the registered version, unless yours already exists.
# LOOK FOR: "Endpoint ready" and a link; or a note that the step was skipped or the endpoint already exists.
endpoint_ready = False
if deploy_approved and version is None:
    print("Register the model first (section 4): there is no version to serve.")
elif deploy_approved:
    from databricks.sdk.service.serving import EndpointCoreConfigInput, EndpointTag, ServedEntityInput

    if endpoint_for_cleanup(A8, w, A8.agent_endpoint_name) is not None:
        print("An endpoint with this name already exists and is yours; it was not changed.")
    else:
        w.serving_endpoints.create_and_wait(
            name=A8.agent_endpoint_name,
            config=EndpointCoreConfigInput(name=A8.agent_endpoint_name, served_entities=[
                ServedEntityInput(entity_name=A8.agent_model_name, entity_version=str(version.version),
                                  workload_size="Small", scale_to_zero_enabled=True)]),
            tags=[EndpointTag(key=k, value=v) for k, v in A8.course_tags.items()])
        print("Endpoint ready.")
    endpoint_ready = True
    A8.links(("Your agent endpoint: status and logs", "endpoint", A8.agent_endpoint_name))
else:
    print("Serving skipped. The registered model is the core outcome.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Query the endpoint
# MAGIC The same five questions, now over HTTPS. The request is a table of questions; the reply is a table of answers.
# MAGIC The first call after a pause can be slow because the endpoint scales to zero.
# MAGIC
# MAGIC **Predict:** will the endpoint's answers be word for word the same as the local ones? Why or why not?

# COMMAND ----------

# WHAT: sends the five questions to your endpoint in one request and prints each answer.
# LOOK FOR: five answers; the seat questions carry the numbers from the snapshot.
served = None
if endpoint_ready:
    reply = w.api_client.do("POST", f"/serving-endpoints/{A8.agent_endpoint_name}/invocations",
                            body={"dataframe_records": [{"question": t["task"]} for t in TASKS]})
    served = reply["predictions"]
    for task, prediction in zip(TASKS, served, strict=True):
        print(f"Q: {task['task']}\nA: {prediction['answer'][:200]}\nsteps: {prediction['steps']}\n")
else:
    print("Skipped: no endpoint to query.")

# COMMAND ----------

# WHAT: Check: the endpoint answers match the local code and the released model.
# LOOK FOR: two pass messages; a difference means the endpoint runs a different version from the one you tested.
if served is not None:
    A8.expect([p["answer"] for p in served] == [r["answer"] for r in local],
              "The endpoint answers exactly as the code you tested.")
    A8.expect(sum(grounded(p["answer"], t) for p, t in zip(served, TASKS, strict=True)) >= 4,
              "The endpoint is at least as good as the baseline (4 of 5 grounded).")
else:
    print("Skipped: no endpoint answers to check.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Govern it
# MAGIC Governance answers three questions: **who can use it, who can change it, and what is running?** These cells
# MAGIC only read. They show the owner and any grants on the model, who may query the endpoint, and which version
# MAGIC the endpoint serves. Right now only you can use all of it. In a real workspace you would grant a group
# MAGIC `EXECUTE` on the model and `CAN QUERY` on the endpoint, and keep change rights to a small team.
# MAGIC
# MAGIC **Staleness.** The snapshot holds seat numbers from when you logged. The agent will keep giving those numbers
# MAGIC until you log a new version and move the alias. That is the cost of a self-contained model, and the reason
# MAGIC live data is normally read through a governed connection instead.

# COMMAND ----------

# WHAT: prints the model's owner, aliases and grants, and the version the endpoint serves.
# LOOK FOR: you as the owner, the Champion alias on your version, and no other principals with grants.
if version is not None:
    base = "/api/2.1/unity-catalog"  # the REST reads below behave the same in every SDK version
    model = w.api_client.do("GET", f"{base}/models/{A8.agent_model_name}", query={"include_aliases": "true"})
    print("Model owner:", model.get("owner"))
    print("Aliases:", {a["alias_name"]: a["version_num"] for a in model.get("aliases", [])})
    try:
        grants = w.api_client.do("GET", f"{base}/permissions/registered_model/{A8.agent_model_name}")
        print("Grants:", [(g["principal"], g["privileges"]) for g in grants.get("privilege_assignments", [])]
              or "none beyond ownership")
    except Exception as error:  # a read failure should not stop the lesson
        print("Grants could not be read:", type(error).__name__)
else:
    print("Skipped: no registered model.")

# COMMAND ----------

# WHAT: prints who may use the endpoint and which model version it serves.
# LOOK FOR: your own account with the manage permission, and the same version number you registered.
if endpoint_ready:
    endpoint = w.serving_endpoints.get(A8.agent_endpoint_name)
    served_versions = [(e.entity_name, e.entity_version) for e in endpoint.config.served_entities]
    print("Serving:", served_versions)
    try:
        acl = w.serving_endpoints.get_permissions(endpoint.id).access_control_list or []
        print("Who can use it:", [(a.user_name or a.group_name or a.service_principal_name,
                                   [p.permission_level.value for p in a.all_permissions or []]) for a in acl])
    except Exception as error:
        print("Permissions could not be read:", type(error).__name__)
else:
    print("Skipped: no endpoint.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Remove the endpoint
# MAGIC The endpoint is the part that can bill, so remove it now. The model stays in Unity Catalog (it costs
# MAGIC nothing to keep) until `99_pause_and_cleanup` removes it with your other course objects. Deletion checks
# MAGIC that you created the endpoint and that it carries your course tags, so it cannot touch anyone else's.
# MAGIC
# MAGIC **Undo:** to serve again, run section 6 again; it creates a new endpoint for the Champion version.

# COMMAND ----------

# WHAT: asks for your approval before deleting your agent endpoint.
# LOOK FOR: a delete_agent_endpoint widget above the notebook, defaulting to no. Set it to yes, then rerun.
delete_approved = A8.gate("delete_agent_endpoint", "Delete your agent serving endpoint?")
print("Approved." if delete_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: deletes your agent endpoint, only if you approved and it is yours.
# LOOK FOR: "Deleted." or a note that there was nothing to delete.
if delete_approved:
    if endpoint_for_cleanup(A8, w, A8.agent_endpoint_name) is None:
        print("There is no agent endpoint of yours to delete.")
    else:
        w.serving_endpoints.delete(A8.agent_endpoint_name)
        print("Deleted.")
else:
    print("Not deleted. Run this section or 99_pause_and_cleanup before you finish.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 10. Your turn
# MAGIC The snapshot holds the seat numbers the deployed agent will report. These two exercises ask what it would say
# MAGIC for events that matter to a customer, in SQL on the availability view, with **no model**.
# MAGIC 1. Exercise 12.1: scheduled events with fewer than 40 seats left, fewest first.
# MAGIC 2. Exercise 12.2: total seats left in scheduled events for each city, largest first.
# MAGIC
# MAGIC Use `IDENTIFIER(a8_event_availability)` for the view name. A blank answer shows the task and a hint.
# MAGIC `A8.solution("12.1")` shows a worked answer. You can also answer with a Spark or pandas DataFrame.

# COMMAND ----------

# WHAT: Check: compares your exercise 12.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_12_1 = """"""
A8.check("12.1", answer_12_1)

# COMMAND ----------

# WHAT: Check: compares your exercise 12.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_12_2 = """"""
A8.check("12.2", answer_12_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 11. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: what would you need to add so that the deployed
# MAGIC agent read **live** seat numbers and could call a chat model, and what new risks would that bring?
# MAGIC
# MAGIC **Completion requires:** both exercises, the checks above, your explanations and, if you approved them, the
# MAGIC register and serve steps and the endpoint deletion. Being blocked on a cloud step is fine: record it, and do
# MAGIC not count that outcome as complete.
# MAGIC
# MAGIC **Pause:** this lesson created one MLflow run, one model and, if you served it, one endpoint. Delete the
# MAGIC endpoint above; `99_pause_and_cleanup` removes the endpoint and the model.
# MAGIC **Next:** `99_pause_and_cleanup`.

# COMMAND ----------
# WHAT: asks why a registered, aliased model is better than the notebook agent for other systems to use.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_12_a = """"""
A8.reflect("12.a", my_answer_12_a)

# COMMAND ----------
# WHAT: asks what goes stale in a snapshot-based model and how to fix it.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_12_b = """"""
A8.reflect("12.b", my_answer_12_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["The agent packaged as plain code with a snapshot, tested before release",
              "An MLflow run and a Unity Catalog model version with a Champion alias",
              "A serving endpoint queried over REST and checked against the local answers",
              "A read of who can use the model and endpoint, and a scoped deletion"],
             "13_pipelines_and_jobs", "Keep the numbers fresh with a pipeline and a job")
