# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | Pause, resume or finish
# MAGIC **Outcome:** know what remains, remove an optional billable endpoint, or explicitly delete your course data.
# MAGIC Settings and source notebooks are never deleted here. No wildcards, schema drops or shared-resource changes.
# MAGIC
# MAGIC ## Pause is not the same as delete
# MAGIC - **Notebook/serverless compute:** idles automatically; classic clusters/warehouses follow their own auto-stop
# MAGIC   settings.
# MAGIC - **Delta tables, volumes, MLflow and UC models:** persist and use storage.
# MAGIC - **Module 1b dashboard drafts and Genie spaces:** persist separately. This notebook does not delete them,
# MAGIC   conversations or cached results. Follow Module 1b's exact-URL/ID UI cleanup before dropping its
# MAGIC   reporting view.
# MAGIC - **Custom model serving:** can keep billing even when your notebook is closed. Delete the endpoint when not
# MAGIC   needed.
# MAGIC - **Later Vector Search/app modules:** not created by this release; their lifecycle will be taught with them.
# MAGIC
# MAGIC To resume, reopen the next lesson and run its configuration cell. Saved settings reload from your workspace user
# MAGIC folder.
# MAGIC Rerun Module 1 only if you intend to reset its source fixtures; rerun Module 3 to create a new model version.
# MAGIC
# MAGIC The next two cells install the MLflow client this notebook needs and restart Python, as in Module 3.
# MAGIC A red pip dependency message about `databricks-agents` is expected and harmless here.

# COMMAND ----------
# MAGIC %pip install mlflow-skinny==3.6.0 typing_extensions==4.15.0

# COMMAND ----------

# WHAT: restarts Python so the installed package version is used.
# LOOK FOR: the Python session restarts; run _config next to reload your settings.
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the clients and course cleanup plumbing.
# LOOK FOR: no output; imports are kept together after configuration.
import mlflow
from databricks.sdk import WorkspaceClient
from mlflow import MlflowClient

from a8learn import OBJECTS
from a8learn.lifecycle import cleanup

# COMMAND ----------
# WHAT: connects the workspace and Unity Catalog model-registry clients.
# LOOK FOR: no output; creating a client does not delete or deploy anything.
w = WorkspaceClient()
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()

# COMMAND ----------
# WHAT: previews the exact names this course can clean up for your tag.
# LOOK FOR: your endpoint name and one line per object; nothing is deleted.
print("Exact endpoint candidate:", A8.endpoint_name)
for key, (kind, _) in OBJECTS.items():
    print(f"{kind:8} {A8.t(key)}")

# COMMAND ----------
# WHAT: opens the pages for inspecting your endpoint and data.
# LOOK FOR: links to Serving and your schema; opening links does not delete anything.
A8.links(("Serving: check whether your endpoint exists", "serving", ""),
         ("Your data objects", "schema", ""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Choose deliberately
# MAGIC `endpoint_only` deletes the exact endpoint after checking creator and course tags.
# MAGIC `all_course_objects` additionally drops the named views/tables/functions/volume, all versions and aliases
# MAGIC of this course model, and soft-deletes this course MLflow experiment.
# MAGIC It deletes uploaded CSV files inside the course volume too. Delta/model/MLflow retention policies can retain
# MAGIC underlying storage; this is not a secure erasure or immediate cost-zero guarantee.
# MAGIC "All course objects" here means the listed UC/MLflow objects and endpoint, not dashboard/Genie UI assets.
# MAGIC A retained dashboard or Genie space will stop querying successfully after its event_metrics view is dropped.
# MAGIC A missing object is fine; a permissions failure or ownership mismatch stops deletion.
# MAGIC
# MAGIC Set the action, type your tag in `confirm_tag`, then rerun the choice, cleanup, result and Check cells below.
# MAGIC **Default is preview only.** To keep your data and stop optional serving charges choose `endpoint_only`.

# COMMAND ----------

# WHAT: collects your explicit cleanup choice and learner-tag confirmation.
# LOOK FOR: cleanup_action defaults to preview; confirm_tag must match before any deletion.
dbutils.widgets.dropdown("cleanup_action", "preview",
                         ["preview", "endpoint_only", "all_course_objects"], "Cleanup action")
dbutils.widgets.text("confirm_tag", "", "Type your learner tag to delete")
action = dbutils.widgets.get("cleanup_action")

# COMMAND ----------
# WHAT: performs only the cleanup you explicitly selected, after ownership checks.
# LOOK FOR: Preview only, or the deletion result; an ownership mismatch stops deletion.
if action == "preview":
    print("Preview only. Nothing deleted.")
else:
    result = cleanup(A8, w, client, dbutils.widgets.get("confirm_tag"),
                     tables=action == "all_course_objects")

# COMMAND ----------
# WHAT: shows the cleanup result without issuing another deletion.
# LOOK FOR: the summary of what was deleted, unless you chose preview.
if action != "preview":
    print(result)

# COMMAND ----------
# WHAT: Check: verifies all course UC objects are absent after full cleanup.
# LOOK FOR: a pass message; settings and source remain for a fresh start.
if action == "all_course_objects":
    remaining = [k for k in OBJECTS if A8.exists(k)]
    A8.expect(not remaining, f"All course UC objects must be absent; still visible: {remaining}")
    print("All course UC objects are absent. Settings/source remain for a fresh start.")
