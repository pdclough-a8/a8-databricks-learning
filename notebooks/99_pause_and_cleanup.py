# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | Pause, resume or finish
# MAGIC **Outcome:** know what remains, remove an optional billable endpoint, or explicitly delete your course data.
# MAGIC Settings and source notebooks are never deleted here. No wildcards, schema drops or shared-resource changes.
# MAGIC
# MAGIC ## Pause is not the same as delete
# MAGIC - **Notebook/serverless compute:** idles automatically; classic clusters/warehouses follow their own auto-stop settings.
# MAGIC - **Delta tables, volumes, MLflow and UC models:** persist and use storage.
# MAGIC - **Custom model serving:** can keep billing even when your notebook is closed. Delete the endpoint when not needed.
# MAGIC - **Later Vector Search/app modules:** not created by this release; their lifecycle will be taught with them.
# MAGIC
# MAGIC To resume, reopen the next lesson and run its configuration cell. Saved settings reload from your workspace user folder.
# MAGIC Rerun Module 1 only if you intend to reset its source fixtures; rerun Module 3 to create a new model version.
# MAGIC
# MAGIC The next two cells install the MLflow client this notebook needs and restart Python, as in Module 3.
# MAGIC A red pip dependency message about `databricks-agents` is expected and harmless here.

# COMMAND ----------
# MAGIC %pip install mlflow-skinny==3.6.0 typing_extensions==4.15.0

# COMMAND ----------
# WHAT: restarts Python so the package just installed is the one imported.
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
# WHAT: lists the exact names of every object this course can create for your tag. Nothing is deleted.
# LOOK FOR: your endpoint name, then one line per object, and links to Serving and your schema.
from a8learn import OBJECTS
from a8learn.lifecycle import cleanup
from databricks.sdk import WorkspaceClient
import mlflow
from mlflow import MlflowClient

w = WorkspaceClient()
mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
print("Exact endpoint candidate:", A8.endpoint_name)
for key, (kind, _) in OBJECTS.items():
    print(f"{kind:8} {A8.t(key)}")
A8.links(("Serving: check whether your endpoint exists", "serving", ""),
         ("Your data objects", "schema", ""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Choose deliberately
# MAGIC `endpoint_only` deletes the exact endpoint after checking creator and course tags.
# MAGIC `all_course_objects` additionally drops the named views/tables/functions/volume, all versions and aliases
# MAGIC of this course model, and soft-deletes this course MLflow experiment.
# MAGIC It deletes uploaded CSV files inside the course volume too. Delta/model/MLflow retention policies can retain underlying storage;
# MAGIC this is not a secure erasure or immediate cost-zero guarantee.
# MAGIC A missing object is fine; a permissions failure or ownership mismatch stops deletion.
# MAGIC
# MAGIC Set the action, type your tag in `confirm_tag`, then rerun the final cell.
# MAGIC **Default is preview only.** To keep your data and stop optional serving charges choose `endpoint_only`.

# COMMAND ----------
# WHAT: does nothing on preview; otherwise deletes exactly what you chose, after ownership checks.
# LOOK FOR: "Preview only", or a summary of what was deleted. A PermissionError means nothing was deleted.
dbutils.widgets.dropdown("cleanup_action", "preview", ["preview", "endpoint_only", "all_course_objects"], "Cleanup action")
dbutils.widgets.text("confirm_tag", "", "Type your learner tag to delete")
action = dbutils.widgets.get("cleanup_action")
if action == "preview":
    print("Preview only. Nothing deleted.")
else:
    result = cleanup(A8, w, client, dbutils.widgets.get("confirm_tag"),
                     tables=action == "all_course_objects")
    print(result)
    if action == "all_course_objects":
        remaining = [k for k in OBJECTS if A8.exists(k)]
        assert not remaining, f"Objects still visible: {remaining}"
        print("All course UC objects are absent. Settings/source remain for a fresh start.")
