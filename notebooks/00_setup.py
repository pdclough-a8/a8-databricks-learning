# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 0. Your Databricks workbench
# MAGIC **Where this sits:** platform foundations for every analytics level, not a separate analytics level.
# MAGIC
# MAGIC **By the end of this notebook you will have:**
# MAGIC - a notebook running on serverless compute
# MAGIC - a schema you know you can write to
# MAGIC - saved settings that every later lesson reloads automatically
# MAGIC - a plain-English picture of the business and the four kinds of analytics the course teaches
# MAGIC
# MAGIC Allow 45–60 minutes. Later lessons take about an hour each. You do not need Python installed on your laptop,
# MAGIC and you do not need to know the events or analytics vocabulary: this notebook explains it.
# MAGIC
# MAGIC ## Which workspace? Start on Free, fall back to paid
# MAGIC This course is built to run in **both** a **Databricks Free Edition** workspace and a **paid** workspace
# MAGIC (AWS, Azure or Google Cloud). Clone this repository into each one you have.
# MAGIC 1. **Start in Free Edition.** It costs nothing, and the lessons are written for it first.
# MAGIC 2. **If a step is blocked** (a feature is missing, a quota is reached or a permission is refused), do not
# MAGIC    work around it. Note the lesson and cell, then repeat that lesson in your **paid** workspace.
# MAGIC 3. **Each workspace is separate.** Tables, models and saved settings do not move between them. In the paid
# MAGIC    workspace, run `00_setup`, then `01_lakehouse_data`, then any earlier lesson the one you need relies on
# MAGIC    (each notebook says what it needs), then the lesson that was blocked. The data is synthetic and ships in
# MAGIC    this repository, so there is nothing to export.
# MAGIC 4. **Paid workspaces may cost money and are usually managed by an administrator.** Ask before you create
# MAGIC    anything, use only a schema you have been given, and read each lesson's cost notes first.
# MAGIC 5. Never copy credentials, tokens or real customer data between workspaces.
# MAGIC
# MAGIC ## The business in plain English
# MAGIC **A8 Events** is a fictional company that runs training events: workshops, briefings and forums on AI, data
# MAGIC engineering, analytics and leadership. Events are held in person (Leeds, Manchester, London, Bristol), online
# MAGIC or both. All of the data is invented and frozen at **20 November 2026**, so every learner sees the same numbers.
# MAGIC
# MAGIC Three tables describe the business. Each row is one thing:
# MAGIC
# MAGIC | Table | One row is… | Examples of columns |
# MAGIC |---|---|---|
# MAGIC | `events` | one event we run | city, date, **capacity** (seats), price, status |
# MAGIC | `bookings` | one customer order for an event | tickets, ticket type, status, whether they attended |
# MAGIC | `feedback` | one comment left after an event | rating from 1 to 5, comment text |
# MAGIC
# MAGIC Words you will meet, and what they mean here:
# MAGIC - **Capacity:** the number of seats at an event. Selling more tickets than capacity is **overbooking**.
# MAGIC - **Booking and ticket:** a booking is one order. It can hold several **tickets**, and each ticket is a seat.
# MAGIC   To count seats taken, count tickets, not bookings.
# MAGIC - **Confirmed and cancelled:** a cancelled booking gives its seats back, so do not count it as taking one.
# MAGIC - **Completed and scheduled:** a completed event has happened; a scheduled event is still to come.
# MAGIC - **Attended and no-show:** after a completed event we know who turned up. A **no-show** booked but did not
# MAGIC   come. For a scheduled event this is **unknown**, which is not the same as no-show.
# MAGIC - **Lead time:** how many days before the event the booking was made.
# MAGIC
# MAGIC ## The four questions analytics answers
# MAGIC Analytics is using data to support a decision. It helps to know which question you are asking.
# MAGIC
# MAGIC | Kind | Question | A8 Events example | Lesson |
# MAGIC |---|---|---|---|
# MAGIC | **Descriptive** | What happened, or what is booked? | How many seats are sold for next month's events? | 3 |
# MAGIC | **Diagnostic** | Why did it happen? | Why do some cities have more no-shows? | 4 |
# MAGIC | **Predictive** | What is likely to happen? | How many of the people booked will turn up? | 5 |
# MAGIC | **Prescriptive** | What should we do? | How many extra tickets can we safely sell? | 6 |
# MAGIC
# MAGIC Each question builds on the one before. Lessons 1 and 2 prepare the data and control access. Lesson 7 adds
# MAGIC generative AI to read feedback comments. Databricks is the subject of the course: the business case gives the
# MAGIC features something real to work on, and each lesson explains the analytics idea before using it.
# MAGIC
# MAGIC ## The journey
# MAGIC 1. `01_lakehouse_data`: load events, bookings and feedback into governed Delta tables
# MAGIC 2. `02_governance`: protect customer contact details
# MAGIC 3. `03_descriptive_analytics`: describe the business with an AI/BI dashboard and Genie
# MAGIC 4. `04_diagnostic_analytics`: find out why a difference exists
# MAGIC 5. `05_predictive_ml`: predict who will turn up, and track the model
# MAGIC 6. `06_prescriptive_analytics`: decide how many tickets to sell and meals to order
# MAGIC 7. `07_genai` (optional): read feedback comments with a foundation model
# MAGIC 8. `08a_embeddings` (optional): find comments by meaning with embeddings
# MAGIC 9. `08b_rag` (optional): answer customer questions from our own documents with retrieval
# MAGIC 10. `08c_vector_search` (optional): a managed Vector Search index; the endpoint bills until deleted
# MAGIC 11. `09_agents` (optional): an agent that chooses between two read-only tools, with a step cap and a trace
# MAGIC 12. `99_pause_and_cleanup`: stop safely and remove what you created
# MAGIC
# MAGIC ## How to read these notebooks
# MAGIC - **Text cells** like this one explain the idea. **Code cells** do the work.
# MAGIC - Every code cell starts with two comments: **WHAT** it does, and what to **LOOK FOR** in its output.
# MAGIC - **Predict** prompts ask you to guess a result before running. A wrong guess is useful: it shows what to look
# MAGIC   at.
# MAGIC - **If it differs / Undo** notes sit under cells that write something, so you know what to do if the result is
# MAGIC   not what is described, and how to reverse it.
# MAGIC - **In your own words** cells ask for one or two sentences, then show a model answer to compare with.
# MAGIC - Lines starting `A8.` call small course helpers that handle names and safety checks, so the Databricks
# MAGIC   code stays in view. Lesson 1 explains them.
# MAGIC - Run one cell at a time with **Shift+Enter**. Avoid **Run all** until you have read a lesson's cost notes.
# MAGIC
# MAGIC ## Choose your route: SQL, Python or both
# MAGIC Databricks supports both languages and each has a natural home. **SQL** is the language of governance, views,
# MAGIC dashboards and AI Functions, so the platform features are taught in SQL. **Python** (pandas, PySpark,
# MAGIC scikit-learn) is where most analysis and machine learning is done.
# MAGIC
# MAGIC Every lesson works in SQL. Where the analysis could equally be done in Python, the lesson adds a **Python
# MAGIC route** (cells marked `PYTHON ROUTE`) that builds the same result in pandas or the Python SDK and **checks it
# MAGIC against the SQL result**. You do not need to do both.
# MAGIC
# MAGIC | If you are mainly a… | Start with | Then |
# MAGIC |---|---|---|
# MAGIC | Analyst or BI developer | the SQL cells and exercises | skim the Python route cells |
# MAGIC | Data scientist or ML engineer | the Python route cells and DataFrame answers | read the SQL too |
# MAGIC | Data engineer | both, comparing the two | |
# MAGIC
# MAGIC Exercises accept a **SQL string, a Spark DataFrame or a pandas DataFrame**: the checker compares the rows, not
# MAGIC the language. A pandas DataFrame is fine for these small tables (`spark.table(...).toPandas()`); for large
# MAGIC tables
# MAGIC you would keep the work in Spark.
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
# MAGIC - **Free Edition:** `workspace` and `default` are filled in for you. Keep them, or use another schema you can
# MAGIC   write to.
# MAGIC - **Paid workspace:** replace both widgets with a catalog and schema **you have been given permission to write
# MAGIC   to**, for example your own user schema. Ask your administrator if you are not sure. Do not create catalogs or
# MAGIC   schemas unless they have asked you to.
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
# LOOK FOR: no output; the widgets below suggest your tag from your sign-in name.
user = spark.sql("SELECT current_user()").first()[0]
host = "https://" + spark.conf.get("spark.databricks.workspaceUrl")

# COMMAND ----------
# WHAT: creates the seven saved-settings input boxes.
# LOOK FOR: widgets above the notebook; edit them before validating your choices.
# These are the Free Edition names. On a paid workspace, replace both with a schema you may write to.
dbutils.widgets.text("catalog", "workspace", "1 Catalog")
dbutils.widgets.text("schema", "default", "2 Existing schema")
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
# MAGIC three parts: **catalog.schema.object**, for example `workspace.default.a8_jsmith_events`.
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
# MAGIC ### In your own words
# MAGIC Answer these two questions from the business primer above, then run each cell to compare.

# COMMAND ----------
# WHAT: asks you to explain event, booking and ticket in your own words.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_0_1 = """"""
A8.reflect("0.1", my_answer_0_1)

# COMMAND ----------
# WHAT: asks you to match a business question to a kind of analytics.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_0_2 = """"""
A8.reflect("0.2", my_answer_0_2)

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
