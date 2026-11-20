# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 0. Your Databricks workbench
# MAGIC **By the end of this notebook you will have:**
# MAGIC - a notebook running on serverless compute
# MAGIC - a schema you know you can write to
# MAGIC - saved settings that every later lesson reloads automatically
# MAGIC
# MAGIC Allow 30–45 minutes. Later lessons take about an hour each. You do not need Python installed on your laptop.
# MAGIC
# MAGIC ## The journey
# MAGIC You run **A8 Events**. Across the course you will:
# MAGIC 1. load event, booking and feedback data into governed Delta tables (Module 1)
# MAGIC 2. protect customer contact details (Module 2)
# MAGIC 3. predict who will turn up (Module 3)
# MAGIC 4. add GenAI, retrieval, tools and an app (Modules 4–8, the next release; not needed yet)
# MAGIC
# MAGIC ## How to read these notebooks
# MAGIC - **Text cells** like this one explain the idea. **Code cells** do the work.
# MAGIC - Every code cell starts with two comments: **WHAT** it does, and what to **LOOK FOR** in its output.
# MAGIC - **Predict** prompts ask you to guess a result before running. A wrong guess is useful: it shows what to look at.
# MAGIC - Lines starting `A8.` call small course helpers that handle names and safety checks, so the Databricks
# MAGIC   code stays in view. Module 1 explains them.
# MAGIC - Run one cell at a time with **Shift+Enter**. Avoid **Run all** until you have read a lesson's cost notes.
# MAGIC
# MAGIC ## Your Git folder, and getting updates
# MAGIC This notebook lives in a **Git folder**: your own copy of the course, linked to GitHub. You only ever **pull**.
# MAGIC 1. To update: click the **main** branch button next to the notebook name → check the changed-files list is empty
# MAGIC    (discard your own edits if you do not need them) → **Pull**.
# MAGIC 2. After a pull: compute menu → **Reset environment**, then run the notebook from the top.
# MAGIC 3. Never commit or push. To keep your own experiments, use **File → Clone** and save the copy outside the Git folder.
# MAGIC
# MAGIC Lines such as `<<<<<<<` or `>>>>>>>` in a notebook mean an unresolved conflict. Your tables and settings are
# MAGIC not in the Git folder, so the safe fix is always available: move the Git folder to Trash and clone it again.
# MAGIC The full beginner's guide, with step-by-step fixes, is `docs/git-folders.md` in this folder.
# MAGIC
# MAGIC ## 1. Open the right place (10 minutes)
# MAGIC 1. Open this notebook from your course **Git folder** (Workspace → your folder). Keep `data`, `lib` and `notebooks` together.
# MAGIC 2. In the top bar, choose **Serverless** compute.
# MAGIC 3. Run the next cell.
# MAGIC
# MAGIC Which catalog and schema to use:
# MAGIC - **Free Edition:** `workspace.default`, or another schema you can write to.
# MAGIC - **Azure paid workspace:** `users.pclough`. Do not create schemas there.
# MAGIC
# MAGIC Using a classic cluster instead? Choose Databricks Runtime 16.4 LTS or later with Unity Catalog.
# MAGIC If serverless or a permission is missing, ask your admin. Never borrow someone else's credentials.

# COMMAND ----------
# WHAT: finds the course folder, loads the course helper library, and creates the settings boxes (widgets).
# LOOK FOR: seven input boxes at the top of the notebook, filled with suggested values.
import os
import sys
from pathlib import Path


def _notebook_dir():
    try:
        return Path.cwd()
    except FileNotFoundError:
        # Python's working folder vanishes if a Git pull or merge rewrites it mid-session.
        context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        return Path("/Workspace" + context.notebookPath().get()).parent


_here = _notebook_dir()
# Re-enter the folder by path: imports that scan sys.path fail if the old folder handle is stale.
os.chdir(_here)
# Walk up from this notebook to the folder holding lib/a8learn and data/raw: the root of your Git folder.
ROOT = next((p for p in [_here, *_here.parents]
             if (p / "lib" / "a8learn").is_dir() and (p / "data" / "raw").is_dir()), None)
if ROOT is None:
    raise RuntimeError("Open this notebook inside the full course Git folder.")
# Make the course helper library importable for this session only.
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))
from a8learn import Config, Course, derive_tag, sql_string

# Who is running this notebook, and in which workspace? Defaults differ for Free Edition and Azure.
user = spark.sql("SELECT current_user()").first()[0]
host = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
is_azure = "azuredatabricks.net" in host
# Widgets are input boxes above the notebook. The last three are for later modules; leave them for now.
dbutils.widgets.text("catalog", "users" if is_azure else "workspace", "1 Catalog")
dbutils.widgets.text("schema", "pclough" if is_azure else "default", "2 Existing schema")
dbutils.widgets.text("tag", derive_tag(user), "3 Your unique learner tag")
dbutils.widgets.text("config_profile", "default", "4 Saved settings profile")
dbutils.widgets.text("chat_model", "databricks-meta-llama-3-3-70b-instruct", "5 Chat endpoint (later)")
dbutils.widgets.text("embedding_model", "databricks-gte-large-en", "6 Embedding endpoint (later)")
dbutils.widgets.text("warehouse_id", "", "7 SQL warehouse ID (later)")
print("Widgets are above the notebook. Edit them, then run the next cell.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Choose your namespace (10 minutes)
# MAGIC **Unity Catalog** is Databricks' governance layer. It names every table, view, file volume and model with
# MAGIC three parts: **catalog.schema.object**, for example `workspace.default.a8_pdclough_events`.
# MAGIC - A **catalog** is the top level, often one per environment or team.
# MAGIC - A **schema** groups related objects and is where permissions are usually granted.
# MAGIC - Your **learner tag** goes into every object name, so your `events` table never collides with anyone else's.
# MAGIC   Keep the same tag for the whole course. Choose a new tag only to start a completely separate run.
# MAGIC
# MAGIC Your notebook writes as **you**. Seeing a schema in Catalog does not prove you can create tables in it;
# MAGIC section 3 tests that.
# MAGIC
# MAGIC **Why save settings?** Widgets belong to one notebook and are forgotten when you move on. The next cell saves
# MAGIC your choices to a small file in your workspace user folder, and every later lesson reloads it.
# MAGIC It does **not** create a catalog or schema.

# COMMAND ----------
# WHAT: checks your choices are valid, confirms you can see the schema, and saves your settings.
# LOOK FOR: a table describing your schema, then a "Settings saved" card showing your object prefix.
cfg = Config(
    catalog=dbutils.widgets.get("catalog").strip(),
    schema=dbutils.widgets.get("schema").strip(),
    tag=dbutils.widgets.get("tag").strip(),
    user=user, host=host,
    chat_model=dbutils.widgets.get("chat_model").strip(),
    embedding_model=dbutils.widgets.get("embedding_model").strip(),
    warehouse_id=dbutils.widgets.get("warehouse_id").strip(),
).validate()  # rejects unsafe names and system catalogs before anything touches Databricks
A8 = Course(cfg, spark, display, displayHTML, dbutils, root=ROOT)  # the helper object every lesson uses
display(spark.sql(f"DESCRIBE SCHEMA {A8.schema_fqn}"))  # fails here if the schema is missing or hidden from you
saved = Course.save(cfg, dbutils.widgets.get("config_profile"))  # a small JSON file; no secrets
A8.declare_variables()  # SQL variables such as a8_events, so %sql cells can use your object names
A8.card("Settings saved", f"<p>Namespace: <code>{A8.schema_fqn}</code>. "
        f"Objects start with <code>{A8.prefix}</code>.</p>"
        "<p>Every lesson reloads these settings from disk, even in a new notebook session.</p>")
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""),
         ("Model serving, later", "serving", ""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Prove you can write (10 minutes)
# MAGIC To create tables you need three privileges: **USE CATALOG**, **USE SCHEMA** and **CREATE TABLE**.
# MAGIC Module 1 also needs **CREATE VOLUME**. The next cell creates one empty probe table, reads it and drops it.
# MAGIC It never grants privileges or changes the schema. If it fails, the error message is useful evidence for your admin.
# MAGIC
# MAGIC The probe only runs if you set the new `run_write_probe` widget to **yes**, then run the cell again.
# MAGIC The course uses these yes/no switches for any step that writes, deletes or can cost money.

# COMMAND ----------
# WHAT: if switched on, creates, reads and drops an empty table to prove you can write here.
# LOOK FOR: "CREATE TABLE and SELECT worked", or "Probe skipped" while the widget is still no.
if A8.gate("run_write_probe", "Create and remove an empty probe table?"):
    # Plain CREATE TABLE (not CREATE OR REPLACE) fails rather than replace an existing object.
    spark.sql(f"CREATE TABLE {A8.t('setup_probe')} (id INT) USING DELTA")
    try:
        assert spark.table(A8.t("setup_probe")).count() == 0
        print("CREATE TABLE and SELECT worked.")
    finally:
        spark.sql(f"DROP TABLE {A8.t('setup_probe')}")  # runs even if the check above fails
else:
    print("Probe skipped. Module 1 will exercise actual writes.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Find your way in the UI (10 minutes)
# MAGIC 1. Open **Your schema** from the links above. Find the **Permissions** tab and read your grants without editing them.
# MAGIC 2. Open **SQL editor** and pick an existing SQL warehouse if there is one. A warehouse is compute for SQL.
# MAGIC    The tables live in Unity Catalog and stay there when compute stops. Do not start a second warehouse for this.
# MAGIC 3. Back here, open `01_lakehouse_data` from the file browser and run its first two cells.
# MAGIC    Check that the printed catalog, schema and tag match yours: that proves the saved settings work across notebooks.
# MAGIC
# MAGIC **Check your understanding**
# MAGIC - What survives when a notebook session ends? *(Tables, files and the saved settings.)*
# MAGIC - What does not? *(Python variables, temporary views and SQL session variables.)*
# MAGIC - You change a widget here. What else must you do? *(Rerun the save cell; widgets are not shared.)*
# MAGIC
# MAGIC **Pausing here is safe:** nothing billable was created. Serverless compute switches itself off when idle.

# COMMAND ----------
# WHAT: summarises what you set up and names the next notebook.
A8.next_step(["Persistent learner configuration", "An identified UC namespace and UI navigation"],
             "01_lakehouse_data", "Files to trusted Delta data")
