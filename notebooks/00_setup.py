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
# MAGIC 2. describe the business with an AI/BI dashboard and check Genie answers (Module 1b)
# MAGIC 3. protect customer contact details (Module 2)
# MAGIC 4. predict who will turn up (Module 3)
# MAGIC 5. add GenAI functions, retrieval, tools and an app (Modules 4–8, planned; not needed yet)
# MAGIC
# MAGIC ## How to read these notebooks
# MAGIC - **Text cells** like this one explain the idea. **Code cells** do the work.
# MAGIC - Every code cell starts with two comments: **WHAT** it does, and what to **LOOK FOR** in its output.
# MAGIC - **Predict** prompts ask you to guess a result before running. A wrong guess is useful: it shows what to look
# MAGIC   at.
# MAGIC - Lines starting `A8.` call small course helpers that handle names and safety checks, so the Databricks
# MAGIC   code stays in view. Module 1 explains them.
# MAGIC - Run one cell at a time with **Shift+Enter**. Avoid **Run all** until you have read a lesson's cost notes.
# MAGIC
# MAGIC ## Your Git folder, and getting updates
# MAGIC This notebook lives in a **Git folder**: your own copy of the course, linked to GitHub. You only ever **pull**.
# MAGIC 1. To update: click the **main** branch button next to the notebook name → check the changed-files list is empty
# MAGIC    (discard your own edits if you do not need them) → **Pull**.
# MAGIC 2. After a pull: compute menu → **Reset environment**, then run the notebook from the top.
# MAGIC 3. Never commit or push. To keep your own experiments, use **File → Clone** and save the copy outside the Git
# MAGIC   folder.
# MAGIC
# MAGIC Lines such as `<<<<<<<` or `>>>>>>>` in a notebook mean an unresolved conflict. Your tables and settings are
# MAGIC not in the Git folder, so the safe fix is always available: move the Git folder to Trash and clone it again.
# MAGIC The full beginner's guide, with step-by-step fixes, is `docs/git-folders.md` in this folder.
# MAGIC
# MAGIC ## 1. Open the right place (10 minutes)
# MAGIC 1. Open this notebook from your course **Git folder** (Workspace → your folder). Keep `data`, `lib` and
# MAGIC   `notebooks` together.
# MAGIC 2. In the top bar, choose **Serverless** compute.
# MAGIC 3. Run the following setup cells, one at a time, until the seven widgets appear.
# MAGIC
# MAGIC Which catalog and schema to use:
# MAGIC - **Free Edition:** `workspace.default`, or another schema you can write to.
# MAGIC - **Azure paid workspace:** `users.pclough`. Do not create schemas there.
# MAGIC
# MAGIC Using a classic cluster instead? Choose Databricks Runtime 16.4 LTS or later with Unity Catalog.
# MAGIC If serverless or a permission is missing, ask your admin. Never borrow someone else's credentials.

# COMMAND ----------

# WHAT: imports the Python libraries needed to bootstrap the course.
# LOOK FOR: no output; setup must find the library before it can create A8.
import importlib
import os
import sys
from pathlib import Path

# COMMAND ----------
# WHAT: recovers the notebook directory even after a Git-folder refresh.
# LOOK FOR: no output; the fallback is used only if the current directory handle has gone stale.
def _notebook_dir():
    try:
        return Path.cwd()
    except FileNotFoundError:
        # A Git pull can remove the current directory while Python still holds its handle.
        context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        return Path("/Workspace" + context.notebookPath().get()).parent

# COMMAND ----------
# WHAT: finds the full course Git folder.
# LOOK FOR: no error if lib/a8learn and data/raw are both present.
_here = _notebook_dir()
# Re-enter by path so imports do not use a stale directory handle.
os.chdir(_here)
ROOT = next((p for p in [_here, *_here.parents]
             if (p / "lib" / "a8learn").is_dir() and (p / "data" / "raw").is_dir()), None)
if ROOT is None:
    raise RuntimeError("Open this notebook inside the full course Git folder.")

# COMMAND ----------
# WHAT: loads the course library from this Git folder.
# LOOK FOR: no output; setup can now validate and save your configuration.
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))
# Setup cannot import a8learn until its Git-folder path has been found.
course_library = importlib.import_module("a8learn")
Config = course_library.Config
Course = course_library.Course
derive_tag = course_library.derive_tag

# COMMAND ----------
# WHAT: reads your identity and workspace for suitable widget defaults.
# LOOK FOR: no output; Azure and Free Edition use different suggested namespaces.
user = spark.sql("SELECT current_user()").first()[0]
host = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
is_azure = "azuredatabricks.net" in host

# COMMAND ----------
# WHAT: creates the seven saved-settings input boxes.
# LOOK FOR: widgets above the notebook; edit them before validating your choices.
dbutils.widgets.text("catalog", "users" if is_azure else "workspace", "1 Catalog")
dbutils.widgets.text("schema", "pclough" if is_azure else "default", "2 Existing schema")
dbutils.widgets.text("tag", derive_tag(user), "3 Your unique learner tag")
dbutils.widgets.text("config_profile", "default", "4 Saved settings profile")
dbutils.widgets.text("chat_model", "databricks-meta-llama-3-3-70b-instruct", "5 Chat endpoint (later)")
dbutils.widgets.text("embedding_model", "databricks-gte-large-en", "6 Embedding endpoint (later)")
dbutils.widgets.text("warehouse_id", "", "7 SQL warehouse ID (later)")
print("Widgets are above the notebook. Edit them, then run the validation cells below.")

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
# MAGIC **Why save settings?** Widgets belong to one notebook and are forgotten when you move on. The save cell
# MAGIC below saves your choices to a small file in your workspace user folder, and every later lesson reloads it.
# MAGIC It does **not** create a catalog or schema.

# COMMAND ----------

# WHAT: validates your namespace and builds the A8 course configuration.
# LOOK FOR: no error for safe names outside system catalogs; no catalog or schema is created.
cfg = Config(
    catalog=dbutils.widgets.get("catalog").strip(),
    schema=dbutils.widgets.get("schema").strip(),
    tag=dbutils.widgets.get("tag").strip(),
    user=user, host=host,
    chat_model=dbutils.widgets.get("chat_model").strip(),
    embedding_model=dbutils.widgets.get("embedding_model").strip(),
    warehouse_id=dbutils.widgets.get("warehouse_id").strip(),
).validate()
A8 = Course(cfg, spark, display, displayHTML, dbutils, root=ROOT)
setup_probe = A8.t("setup_probe")

# COMMAND ----------
# WHAT: shows the selected schema to confirm it is visible.
# LOOK FOR: the schema description, or a useful error if it is missing or hidden.
display(spark.sql(f"DESCRIBE SCHEMA {A8.schema_fqn}"))

# COMMAND ----------
# WHAT: saves your validated settings for later notebooks.
# LOOK FOR: a small settings file with no secrets.
saved = Course.save(cfg, dbutils.widgets.get("config_profile"))

# COMMAND ----------
# WHAT: declares SQL variables containing your course object names.
# LOOK FOR: no output; %sql cells can now use IDENTIFIER(a8_events).
A8.declare_variables()

# COMMAND ----------
# WHAT: shows the saved namespace and object prefix.
# LOOK FOR: a Settings saved card confirming what later lessons reload.
A8.card("Settings saved", f"<p>Namespace: <code>{A8.schema_fqn}</code>. "
        f"Objects start with <code>{A8.prefix}</code>.</p>"
        "<p>Every lesson reloads these settings from disk, even in a new notebook session.</p>")

# COMMAND ----------
# WHAT: opens the workspace pages used in this course.
# LOOK FOR: links to your schema, SQL editor and later serving section.
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""),
         ("Model serving, later", "serving", ""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Prove you can write (10 minutes)
# MAGIC To create tables you need three privileges: **USE CATALOG**, **USE SCHEMA** and **CREATE TABLE**.
# MAGIC Module 1 also needs **CREATE VOLUME**. The probe cells create one empty table, read it and drop it.
# MAGIC Create/read/drop deliberately share a `try/finally` safety block so a failed read cannot leave the table behind;
# MAGIC its separate Check cell runs only after the temporary table has been removed.
# MAGIC It never grants privileges or changes the schema. If it fails, the error message is useful evidence for your
# MAGIC admin.
# MAGIC
# MAGIC The probe only runs if you set the new `run_write_probe` widget to **yes**, then rerun its gate, probe and Check
# MAGIC cells.
# MAGIC The course uses these yes/no switches for any step that writes, deletes or can cost money.

# COMMAND ----------

# WHAT: asks for permission to run the write probe.
# LOOK FOR: a run_write_probe widget defaulting to no.
run_write_probe = A8.gate("run_write_probe", "Create and remove an empty probe table?")

# COMMAND ----------
# WHAT: runs a temporary write probe with guaranteed removal.
# LOOK FOR: a successful create/read/drop, or Probe skipped while the widget is no.
if run_write_probe:
    # Plain CREATE refuses to replace an existing object, even one with the same name.
    spark.sql(f"CREATE TABLE {setup_probe} (id INT) USING DELTA")
    try:
        probe_count = spark.table(setup_probe).count()
    finally:
        spark.sql(f"DROP TABLE {setup_probe}")
else:
    print("Probe skipped. Module 1 will exercise actual writes.")

# COMMAND ----------
# WHAT: Check: verifies the probe was readable and empty.
# LOOK FOR: CREATE TABLE and SELECT worked, if you enabled the probe.
if run_write_probe:
    A8.expect(probe_count == 0, "The newly created probe must be readable and contain no rows.")
    print("CREATE TABLE and SELECT worked.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Find your way in the UI (10 minutes)
# MAGIC 1. Open **Your schema** from the links above. Find the **Permissions** tab and read your grants without editing
# MAGIC   them.
# MAGIC 2. Open **SQL editor** and pick an existing SQL warehouse if there is one. A warehouse is compute for SQL.
# MAGIC    The tables live in Unity Catalog and stay there when compute stops. Do not start a second warehouse for this.
# MAGIC 3. Back here, open `01_lakehouse_data` from the file browser and run its configuration cell.
# MAGIC    Check that the printed catalog, schema and tag match yours: that proves the saved settings work across
# MAGIC notebooks.
# MAGIC
# MAGIC **Check your understanding**
# MAGIC - What survives when a notebook session ends? *(Tables, files and the saved settings.)*
# MAGIC - What does not? *(Python variables, temporary views and SQL session variables.)*
# MAGIC - You change a widget here. What else must you do? *(Rerun the save cell; widgets are not shared.)*
# MAGIC
# MAGIC **Pausing here is safe:** nothing billable was created. Serverless compute switches itself off when idle.

# COMMAND ----------

# WHAT: summarises what you set up and names the next notebook.
# LOOK FOR: the saved-configuration checkpoint and Module 1 link.
A8.next_step(["Persistent learner configuration", "An identified UC namespace and UI navigation"],
             "01_lakehouse_data", "Files to trusted Delta data")
