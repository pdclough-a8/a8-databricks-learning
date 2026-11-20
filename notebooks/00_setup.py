# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 0. Your Databricks workbench
# MAGIC **Outcome:** a working notebook, a known writable schema and settings that survive moving between lessons.
# MAGIC Allow 30–45 minutes here, then about 60 minutes per lesson. No local Python or AI coding assistant is required.
# MAGIC
# MAGIC ## The journey
# MAGIC You run A8 Events. First put event, booking and feedback data into governed Delta tables.
# MAGIC Then protect contact details, predict turnout, add GenAI and retrieval, build tools and MCP,
# MAGIC and deploy an interactive app. **This release implements 0–3; 4–8 are the next stage, not hidden prerequisites.**
# MAGIC
# MAGIC ## 1. Open the right place (10 minutes)
# MAGIC In **Workspace**, create a **Git folder** from your course repository. Open this notebook there.
# MAGIC Keep `data`, `lib` and `notebooks` together. Select **Python** and **Serverless** compute in the top bar.
# MAGIC Run one cell with Shift+Enter; use **Run all** only after reading each lesson's write/cost notice.
# MAGIC Grey `%md` cells teach; Python and `%sql` cells execute. Outputs sit below cells.
# MAGIC
# MAGIC **Free Edition:** use `workspace.default` (or an existing writable schema).
# MAGIC **Azure paid:** use `users.pclough`; do not create schemas. Serverless/UC must be enabled.
# MAGIC Existing cluster users need a recent UC-compatible runtime, preferably 16.4 LTS or later.
# MAGIC If serverless or a privilege is missing, ask your admin. Do not switch to shared admin credentials.

# COMMAND ----------
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
ROOT = next((p for p in [_here, *_here.parents]
             if (p / "lib" / "a8learn").is_dir() and (p / "data" / "raw").is_dir()), None)
if ROOT is None:
    raise RuntimeError("Open this notebook inside the full course Git folder.")
sys.path.insert(0, str(ROOT / "lib")) if str(ROOT / "lib") not in sys.path else None
from a8learn import Config, Course, derive_tag, sql_string

user = spark.sql("SELECT current_user()").first()[0]
host = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
is_azure = "azuredatabricks.net" in host
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
# MAGIC Unity Catalog addresses an object as **catalog.schema.object**.
# MAGIC A schema is a namespace and permission boundary, not a Spark session.
# MAGIC A tag makes your objects distinct: `a8_yourtag_events`, not somebody else's `events`.
# MAGIC Keep the same tag for every module. Choose a new tag only to start a separate course run.
# MAGIC
# MAGIC Your notebook identity owns writes. Later, an app runs as its own service principal.
# MAGIC A schema appearing in Catalog does not prove you can create tables in it.
# MAGIC The next cell checks visibility and saves non-secret settings in your user workspace folder.
# MAGIC It does **not** create a catalog or schema.

# COMMAND ----------
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
display(spark.sql(f"DESCRIBE SCHEMA {A8.schema_fqn}"))
saved = Course.save(cfg, dbutils.widgets.get("config_profile"))
A8.declare_variables()
A8.card("Settings saved", f"<p>Namespace: <code>{A8.schema_fqn}</code>. "
        f"Objects start with <code>{A8.prefix}</code>.</p>"
        "<p>Every lesson reloads these settings from disk, even in a new notebook session.</p>")
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""),
         ("Model serving, later", "serving", ""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Prove you can write (10 minutes)
# MAGIC This creates, reads and drops one **empty temporary course probe table** in your selected schema.
# MAGIC It needs USE CATALOG, USE SCHEMA and CREATE TABLE. Module 1 additionally needs CREATE VOLUME.
# MAGIC It never grants you privileges or changes a schema. A failure is useful evidence for your admin.
# MAGIC Turn `run_write_probe` to **yes** to run this optional check.

# COMMAND ----------
if A8.gate("run_write_probe", "Create and remove an empty probe table?"):
    # Never replace an existing object, even one with the same probe name.
    spark.sql(f"CREATE TABLE {A8.t('setup_probe')} (id INT) USING DELTA")
    try:
        assert spark.table(A8.t("setup_probe")).count() == 0
        print("CREATE TABLE and SELECT worked.")
    finally:
        spark.sql(f"DROP TABLE {A8.t('setup_probe')}")
else:
    print("Probe skipped. Module 1 will exercise actual writes.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Find your way in the UI (10 minutes)
# MAGIC Open **Your schema** above. Find **Permissions**, then read your effective grants without editing them.
# MAGIC Open **SQL editor** and choose an existing SQL warehouse if available. A warehouse is SQL compute;
# MAGIC the tables are still in Unity Catalog and remain when compute stops. Do not start a second warehouse just for this step.
# MAGIC Return here. In the file browser open `01_lakehouse_data`, run its first two cells and check that the printed
# MAGIC catalog, schema and tag match. This tests the exact cross-notebook hand-off that widgets alone cannot provide.
# MAGIC
# MAGIC **Check your understanding:** What persists when a notebook session ends? (Tables, files, saved configuration.)
# MAGIC What does not? (Python variables, temporary views and SQL session variables.)
# MAGIC If you change widgets here, rerun the save cell; widgets are not a shared configuration store.
# MAGIC
# MAGIC **Pause:** no endpoint or app was created. Serverless compute idles automatically; your files/settings remain.

# COMMAND ----------
A8.next_step(["Persistent learner configuration", "An identified UC namespace and UI navigation"],
             "01_lakehouse_data", "Files to trusted Delta data")
