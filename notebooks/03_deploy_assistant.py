# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 3. Put it to work
# MAGIC **Outcome:** deploy and check a supplied app, then explain whose identity it uses.
# MAGIC Read `docs/lessons/03-app.md` before enabling any cell.
# MAGIC App compute may bill even when the app uses simulation. UI-led deployment is an equal route.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Prepare this session
# MAGIC Run the next two cells once on approved compute, then run setup.
# MAGIC Package installation does not create an app. If blocked, use the UI route.

# COMMAND ----------
# MAGIC %pip install databricks-sdk==0.67.0 openai==2.14.0

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ./00_start_here

# COMMAND ----------
print({"app": APP_NAME, "description": MARKER, "source": str(ROOT / "app/event_assistant")})

# COMMAND ----------
# MAGIC %md
# MAGIC ## Create the marked app, with the authorised model resource
# MAGIC Existing marked apps are reused, never reconfigured. Inspect their model resource in the UI.
# MAGIC An app-name collision (including tags where underscores become hyphens) stops at the marker check.

# COMMAND ----------
CREATE_MY_APP = False
if CREATE_MY_APP:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    result = ensure_app(w, CATALOG, SCHEMA, TAG, ENDPOINT)
    print("Create/reuse request complete. Inspect your app in Compute > Apps.")
else:
    print("No app created.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Prepare the source and deploy
# MAGIC Wait for app compute readiness in Apps. Grant the app service principal CAN READ on only
# MAGIC your `app/event_assistant` workspace source folder, following the guide. This is a manual grant.
# MAGIC Confirm resource key `model`, selected endpoint and CAN_QUERY.
# MAGIC The next cell snapshots only the app subfolder. Your workspace may disallow workspace-source deployment.

# COMMAND ----------
DEPLOY_MY_APP = False
SOURCE_PATH = str(ROOT / "app" / "event_assistant").replace("\\", "/")
if DEPLOY_MY_APP:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    result = deploy_app(w, CATALOG, SCHEMA, TAG, SOURCE_PATH)
    print("Deployment requested, not verified. Inspect deployment status and open the app.")
else:
    print("No deployment requested.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Verify and explain
# MAGIC Run simulation: Leeds must cite E101=18 and E104=22 and say it is not AI.
# MAGIC Unsupported simulation question must say it is unsupported.
# MAGIC With approval, check live mode, Manchester under ten, then missing cancellation policy.
# MAGIC Notebook calls used your identity; deployed live calls use the app service principal.
# MAGIC Change APP_TITLE in your copy of app.py, redeploy, confirm, then restore and redeploy.
# MAGIC The UI route deploys/configures supplied Python; it is not visual app authoring.
# MAGIC **Finish:** reset flags, save evidence, then read `docs/operations.md` or open `90_finish`.
