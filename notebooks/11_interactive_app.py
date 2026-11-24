# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 11. An interactive app: let colleagues see seats left without opening a notebook
# MAGIC **Where this sits:** deployment for people, not code. Modules 1 to 13 answered questions inside notebooks. A
# MAGIC colleague in the events team will not open a notebook. A **Databricks App** is a small web application that
# MAGIC runs inside your workspace, with its own identity and its own access.
# MAGIC
# MAGIC **Outcome:** read a small Streamlit app, create a Databricks App, give its **service principal** only the access
# MAGIC it needs, deploy it, open it, see who the app runs as and who is viewing it, and remove everything.
# MAGIC
# MAGIC **About 60 minutes, an estimate:** orient 10 · source and settings 10 · create and grant 15 ·
# MAGIC deploy and use 15 · exercise and recap 10.
# MAGIC **Before you start:** finish `00_setup` and `01_lakehouse_data`, and have a SQL warehouse. All data is
# MAGIC synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. Reading the source needs no cloud action. Writing the
# MAGIC source, creating, granting and deploying each sit behind a default-no switch. If a step is blocked, finish the
# MAGIC rest and repeat it in your paid workspace.
# MAGIC
# MAGIC **Cost boundary:** this lesson creates **one app** and one small folder of source files. An app keeps compute
# MAGIC running while it exists and uses quota on Free or money on a paid workspace. Delete it in the last section, or
# MAGIC with `99_pause_and_cleanup`. Free Edition allows one app at a time. The app is read-only: it cannot change any
# MAGIC data.
# MAGIC
# MAGIC ## Apps in plain English
# MAGIC You write ordinary Python and give Databricks a start command. Databricks runs it behind a sign-in page, so only
# MAGIC people you allow can open it. Two identities matter:
# MAGIC - **The app's service principal:** an identity created for the app. The app's code uses it to query data, so
# MAGIC   it can read only what you grant it.
# MAGIC - **The viewer:** the person who opened the page. Databricks tells the app their email in a header, which
# MAGIC   the app can show, but this app does not use their access.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **App** | a web application that Databricks runs and signs people in to |
# MAGIC | **Service principal** | the identity the app uses to reach data |
# MAGIC | **Resource** | something the app may use, here a SQL warehouse; the app reads its id with `valueFrom` |
# MAGIC | **Deployment** | one copy of your source files running as the app |
# MAGIC | **Least privilege** | granting only what the app needs: here `SELECT` on one view |
# MAGIC
# MAGIC **Business question for this lesson:** *how do we let the events team see seats left without giving them
# MAGIC access to the bookings table?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
# MAGIC - [App authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; app_deploy builds the settings file and finds only your own app.
import time
import urllib.request

from a8learn import quote
from a8learn.app_deploy import app_description, app_for_cleanup, app_yaml, delete_app
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import App, AppDeployment, AppResource, AppResourceSqlWarehouse
from databricks.sdk.service.apps import AppResourceSqlWarehouseSqlWarehousePermission as WarehousePermission
from databricks.sdk.service.workspace import ImportFormat

# COMMAND ----------

# WHAT: checks the prerequisites, finds the SQL warehouse and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming your app, the view it reads and the warehouse.
A8.require("events", "bookings", "event_availability")
w = WorkspaceClient()
availability = A8.t("event_availability")
warehouse_id = A8.cfg.warehouse_id
if not warehouse_id:
    warehouses = list(w.warehouses.list())
    A8.expect(len(warehouses) == 1, "Set warehouse_id in 00_setup: this workspace has no single obvious warehouse.")
    warehouse_id = warehouses[0].id
print(f"Ready | app {A8.app_name} | reads {availability} | warehouse {warehouse_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Read the app
# MAGIC The app is one Python file in your Git folder. It is **read-only**: one `SELECT` on the availability view
# MAGIC from Module 1, a city filter, a threshold, a chart and a panel that names the two identities. **Look for:** the
# MAGIC two settings it reads from the environment (`A8_WAREHOUSE_ID` and `A8_VIEW`), and the one header it reads to
# MAGIC find the viewer.
# MAGIC
# MAGIC **Predict:** the app queries on its own. Which identity's access decides whether the query succeeds?

# COMMAND ----------

# WHAT: prints the app source.
# LOOK FOR: os.environ for the two settings, execute_statement for the query, X-Forwarded-Email for the viewer.
print((ROOT / "app" / "a8_events" / "app.py").read_text(encoding="utf-8"))

# COMMAND ----------

# WHAT: prints the settings file generated for your app, with your own view name.
# LOOK FOR: the start command, the warehouse taken from the resource with valueFrom, and your view name.
print(app_yaml(A8))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Create the app
# MAGIC Three steps, each behind its own switch because each changes your workspace:
# MAGIC 1. **Write the source** to a folder in your workspace user area (`app.py`, `app.yaml`, and nothing else).
# MAGIC 2. **Create the app**, with your warehouse as a **resource** so the app's service principal can use it, and a
# MAGIC    course marker in its description so cleanup only ever deletes yours.
# MAGIC 3. **Grant** that service principal `SELECT` on the view, plus the `USE` rights needed to reach it (section 3).
# MAGIC
# MAGIC Set `create_app` to **yes** only if you accept the quota or cost. **If it differs:** a permission message means
# MAGIC apps are not available in this workspace; read the rest and repeat in your paid workspace. A message about a
# MAGIC limit on apps means another app already exists: delete it or use another workspace. **Undo:** the last
# MAGIC section, or `99_pause_and_cleanup`.

# COMMAND ----------

# WHAT: asks for your approval before the source is written and the app is created.
# LOOK FOR: a create_app widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
create_approved = A8.gate("create_app", "Write the app source and create your app (compute runs while it exists)?")
print("Approved." if create_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: writes your app's source folder and creates the app, or finds the one you already created.
# LOOK FOR: the app's service principal name; this is the identity that will query your data.
app = None
if create_approved:
    existing = app_for_cleanup(A8, w)  # refuses an app with this name that is not yours
    if existing is not None:
        app = existing
        print("An app with this name already exists and is yours; it was not changed.")
    else:
        w.workspace.mkdirs(A8.app_folder)
        w.workspace.upload(f"{A8.app_folder}/app.py", (ROOT / "app" / "a8_events" / "app.py").read_bytes(),
                           format=ImportFormat.AUTO, overwrite=True)
        w.workspace.upload(f"{A8.app_folder}/app.yaml", app_yaml(A8).encode(),
                           format=ImportFormat.AUTO, overwrite=True)
        app = w.apps.create_and_wait(app=App(
            name=A8.app_name, description=app_description(A8),
            resources=[AppResource(name="warehouse", sql_warehouse=AppResourceSqlWarehouse(
                id=warehouse_id, permission=WarehousePermission.CAN_USE))]))
        print("Created", app.name)
    print("Service principal:", app.service_principal_name)
else:
    print("Skipped. Reading the app above is the core outcome; the rest needs this step.")

# COMMAND ----------

# WHAT: Check: the app exists, is yours, and is attached to your warehouse.
# LOOK FOR: three pass messages; skipped if you have not created the app.
if app is not None:
    A8.expect(app.creator == A8.cfg.user, "The app was created by you.")
    A8.expect((app.description or "") == app_description(A8), "The app carries your course marker.")
    A8.expect(any(r.sql_warehouse and r.sql_warehouse.id == warehouse_id for r in app.resources or []),
              "The app has your warehouse as a resource.")
else:
    print("Skipped: the app has not been created.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Give the app access to one view
# MAGIC The app's service principal starts with **no** access to your data. A view is the right thing to share: it
# MAGIC shows seats left without exposing the bookings table or anyone's email. The three grants are `USE CATALOG` and
# MAGIC `USE SCHEMA` (permission to reach the view) and `SELECT` on the view itself. Nothing else is granted.
# MAGIC
# MAGIC Set `grant_app_access` to **yes** to apply them. **Undo:** the last section revokes them.

# COMMAND ----------

# WHAT: asks for your approval before access is granted to the app's service principal.
# LOOK FOR: a grant_app_access widget above the notebook, defaulting to no. Set it to yes, then rerun.
grant_approved = A8.gate("grant_app_access", "Grant your app's service principal SELECT on the availability view?")
print("Approved." if grant_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: grants the three privileges to the app's service principal, using its application id.
# LOOK FOR: three statements; the app now holds only these.
if grant_approved and app is not None:
    principal = f"`{app.service_principal_client_id}`"
    for statement in (f"GRANT USE CATALOG ON CATALOG {quote(A8.cfg.catalog)} TO {principal}",
                      f"GRANT USE SCHEMA ON SCHEMA {A8.schema_fqn} TO {principal}",
                      f"GRANT SELECT ON VIEW {availability} TO {principal}"):
        print(statement)
        spark.sql(statement)
else:
    print("Skipped: needs the app (create_app) and approval (grant_app_access).")

# COMMAND ----------

# WHAT: lists what the app's service principal holds on the view.
# LOOK FOR: one row with SELECT and nothing else.
if grant_approved and app is not None:
    display(spark.sql(f"SHOW GRANTS `{app.service_principal_client_id}` ON VIEW {availability}"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Deploy and use it
# MAGIC **Deploying** copies the source folder into the running app. The path must start with `/Workspace`. Starting
# MAGIC takes a minute or two. Then we ask the app for its page with your own credentials.
# MAGIC
# MAGIC **Predict:** if you had deployed *before* the grants, what would the page have shown? Open the app and look:
# MAGIC the page should show a table, not an error. A red "Could not read seats left" message means the grants in
# MAGIC section 3 are missing. **Undo:** the last section.

# COMMAND ----------

# WHAT: asks for your approval before the app is deployed.
# LOOK FOR: a deploy_app widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
deploy_approved = A8.gate("deploy_app", "Deploy your app (it starts running)?")
print("Approved." if deploy_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: deploys the source folder and waits for the app to run. Not retried in a loop.
# LOOK FOR: deployment state SUCCEEDED and the app RUNNING; a failure message is printed, not hidden.
state = None
if deploy_approved and app is not None:
    deployment = w.apps.deploy_and_wait(
        app_name=A8.app_name, app_deployment=AppDeployment(source_code_path=f"/Workspace{A8.app_folder}"))
    print("Deployment:", deployment.status.state.value, "|", deployment.status.message)
    for _ in range(10):
        app = w.apps.get(A8.app_name)
        state = app.app_status.state.value if app.app_status else None
        if state == "RUNNING":
            break
        time.sleep(15)
    print("App state:", state)
    A8.links(("Your app", "app", A8.app_name))
else:
    print("Skipped: needs the app and approval (deploy_app).")

# COMMAND ----------

# WHAT: Check: the app is running and answers a request made with your own credentials.
# LOOK FOR: two pass messages. The page is a Streamlit shell, so this proves it is served, not what it shows:
# open the link above to see the table.
if state is not None:
    A8.expect(state == "RUNNING", "The app is running.")
    request = urllib.request.Request(app.url, headers=w.config.authenticate())
    with urllib.request.urlopen(request, timeout=60) as reply:
        A8.expect(reply.status == 200, "The app answers a signed-in request.")
else:
    print("Skipped: the app has not been deployed.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Two identities
# MAGIC Open the app and expand **Who is running this, and who is looking at it?** The first line is the service
# MAGIC principal, the second is you. The table is what the service principal can read. A colleague with access to
# MAGIC **only the app** would see the same table even though they cannot read `bookings` themselves.

# COMMAND ----------

# WHAT: shows who you are and who the app runs as, side by side.
# LOOK FOR: your email and the app's service principal name are different identities.
if app is not None:
    print("You:", A8.cfg.user)
    print("The app runs as:", app.service_principal_name)
    A8.expect(app.service_principal_name != A8.cfg.user, "The app runs as a different identity from you.")
else:
    print("Skipped: the app has not been created.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Your turn
# MAGIC One exercise on the view the app reads. It needs no app.
# MAGIC 1. Exercise 11.1: how many scheduled events have fewer than 30 seats left? That is the app's second metric at
# MAGIC    its default threshold.
# MAGIC
# MAGIC Use `IDENTIFIER(a8_event_availability)`. A blank answer shows the task and a hint. `A8.solution("11.1")` shows
# MAGIC a worked answer.

# COMMAND ----------

# WHAT: Check: compares your exercise 11.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_11_1 = """"""
A8.check("11.1", answer_11_1)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Remove what you created
# MAGIC The app is what keeps compute running, so remove it. This revokes the three grants, deletes the app after
# MAGIC checking its name, creator and course marker, and deletes the source folder. Deletion finishes a few
# MAGIC seconds after the call. **Undo:** to build it again, run sections 2 to 4 again.

# COMMAND ----------

# WHAT: asks for your approval before deleting your app.
# LOOK FOR: a delete_app widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
delete_approved = A8.gate("delete_app", "Delete your app, its grants and its source folder?")
print("Approved." if delete_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: deletes your app, its grants and its source folder, only if you approved and the app is yours.
# LOOK FOR: one line saying what was removed, or that there was nothing of yours to remove.
if delete_approved:
    removed = delete_app(A8, w)
    print("Removed your app, its grants and its folder." if removed
          else "There was no app of yours to remove; the source folder was removed if present.")
else:
    print("Not deleted. Run this section or 99_pause_and_cleanup before you finish.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: the app can read the availability view for
# MAGIC everyone who opens it. What would you change before sharing it with a client's staff?
# MAGIC
# MAGIC **Completion requires:** the exercise, the checks above, your explanations and, if you approved them, the
# MAGIC create, grant, deploy and delete steps. Being blocked on a cloud step is fine: record it, and do not count
# MAGIC that outcome as complete.
# MAGIC
# MAGIC **Pause:** this lesson created an app and a folder. Delete them above; `99_pause_and_cleanup` removes both.
# MAGIC **Next:** `99_pause_and_cleanup`.

# COMMAND ----------
# WHAT: asks why the service principal, not the viewer, needs the grants.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_11_a = """"""
A8.reflect("11.a", my_answer_11_a)

# COMMAND ----------
# WHAT: asks what a colleague without access to the bookings table would see.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_11_b = """"""
A8.reflect("11.b", my_answer_11_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["A read-only Streamlit app over the seats-left view",
              "A Databricks App with a warehouse resource and its own service principal",
              "Least-privilege grants for that principal, and a clear view of app versus viewer identity",
              "A scoped removal of the app, its grants and its source folder"],
             "99_pause_and_cleanup", "Pause safely or remove only your course work")
