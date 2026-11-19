# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | Pause or finish
# MAGIC **Pause:** use Apps > your app > Stop; stop your own compute if appropriate.
# MAGIC Do not delete a shared model endpoint. See `docs/operations.md`.
# MAGIC **Final teardown only:** this notebook deletes the exact marked app and table, not the schema.
# MAGIC Back up your learner evidence first. Reads and permission failures can stop cleanup safely.

# COMMAND ----------
# MAGIC %run ./00_start_here

# COMMAND ----------
print({"DELETE_TABLE": TABLE, "DELETE_APP": APP_NAME, "required_marker": MARKER})
CONFIRM_DELETE = ""  # Final deletion only: replace with your exact learner tag.
if CONFIRM_DELETE:
    from databricks.sdk import WorkspaceClient
    print(cleanup(WorkspaceClient(), spark, CATALOG, SCHEMA, TAG, CONFIRM_DELETE))
    print("Check Catalog and Apps for absence. App deletion may be asynchronous.")
else:
    print("Nothing deleted. A stopped app is not a deleted app.")

# COMMAND ----------
# MAGIC %md
# MAGIC Reset confirmation to empty and save. Remove any manual source-folder grant when no longer
# MAGIC needed. Keep your course copy/progress unless you choose otherwise.
# MAGIC If only part of teardown completed, rerun with the same tag after checking the remaining object.
# MAGIC Never use a prefix wildcard or drop the schema to finish this course.
