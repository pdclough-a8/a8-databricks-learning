# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1. Files to trusted lakehouse data
# MAGIC **By the end of this notebook you will have:**
# MAGIC - the raw CSV files in a governed **volume**
# MAGIC - three typed **Delta tables**: events, bookings and feedback
# MAGIC - a reusable **view** showing seats still available
# MAGIC - seen a table's **history** and **lineage** in the UI
# MAGIC
# MAGIC **60 minutes:** orient 5 · files 10 · Delta 15 · SQL and PySpark 15 · history and UI 10 · recap 5.
# MAGIC
# MAGIC **Before you start:** run `00_setup`. This lesson writes only objects with your tag, in your saved schema.
# MAGIC Compute and storage may cost a little. No endpoint, pipeline or app is started.
# MAGIC
# MAGIC ## 1. A lakehouse separates storage, governance and compute
# MAGIC - A **volume** holds files: CSVs, PDFs, images. Think of it as a governed folder.
# MAGIC - A **Delta table** holds rows and columns. It adds a schema, SQL access and a *transaction log* that records
# MAGIC   every change, which is what makes history and time travel possible.
# MAGIC - **Unity Catalog** governs both: names, permissions and lineage.
# MAGIC - **Compute** (this notebook, or a SQL warehouse) reads and writes them. Stop the compute and the data stays.
# MAGIC
# MAGIC The source is synthetic A8 Events data, frozen at **20 November 2026**, not today's date.
# MAGIC
# MAGIC ## Your course toolkit
# MAGIC The next cell runs `_config`, which reloads your settings and creates `A8`. You will meet these helpers:
# MAGIC
# MAGIC | Helper | What it does |
# MAGIC |---|---|
# MAGIC | `{events}` inside SQL | a placeholder replaced by your real name, e.g. `workspace.default.a8_yourtag_events` |
# MAGIC | `A8.run(sql)` | fills in the placeholders, **shows you the exact SQL**, then runs it |
# MAGIC | `A8.sql(sql)` | the same, without showing the SQL; used for reading results |
# MAGIC | `A8.t("events")` | returns your real table name, for Python APIs such as `spark.table(...)` |
# MAGIC | `A8.guard("events")` | a safety check: stops if the object exists but is not yours |
# MAGIC | `A8.links(...)` | shows links that open the matching page in the Databricks UI |
# MAGIC | `A8.check("1.1", answer)` | checks your exercise answer against your own tables |
# MAGIC
# MAGIC Everything else is ordinary Databricks SQL, PySpark or Python.

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
# WHAT: opens links to your schema and the SQL editor, and lists the CSV files shipped with the course.
# LOOK FOR: three file names: bookings.csv, events.csv and feedback.csv.
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""))
print("Source files:", [p.name for p in (ROOT / "data" / "raw").glob("*.csv")])

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Land files in a governed volume (10 minutes)
# MAGIC The CSVs are currently just files in your Git folder. We copy them into a **volume** so Unity Catalog governs
# MAGIC who can read them, and so SQL can read them by path: `/Volumes/catalog/schema/volume/file.csv`.
# MAGIC
# MAGIC `CREATE VOLUME IF NOT EXISTS` is safe to rerun: it does nothing if the volume is already there.
# MAGIC Copying a file is not a database insert; the bytes are simply stored in the volume.
# MAGIC
# MAGIC **UI alternative:** Catalog → your schema → **Create → Volume**, managed, using the name shown below.
# MAGIC Upload the three files from `data/raw`, then skip the next code cell. Never upload real customer data.

# COMMAND ----------
# WHAT: creates your volume (if needed) and copies the three CSV files into it.
# LOOK FOR: the CREATE VOLUME statement that ran, then a listing of three files with their sizes.
import shutil
from a8learn import COURSE_ID

A8.guard("raw")
A8.run("""CREATE VOLUME IF NOT EXISTS {raw}
COMMENT 'a8-databricks-learning managed teaching files'""")
for filename in ["events.csv", "bookings.csv", "feedback.csv"]:
    # Volumes appear as ordinary folders under /Volumes, so standard Python file copying works.
    shutil.copyfile(ROOT / "data" / "raw" / filename, Path(A8.volume_path) / filename)
display(dbutils.fs.ls(A8.volume_path))
A8.links(("Raw files, inspect the CSV preview", "volume", "raw"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Inspect before you ingest (5 minutes)
# MAGIC `read_files` reads files straight from a volume. With `inferSchema` Databricks *guesses* each column's type.
# MAGIC Guessing is fine for a first look but not for a pipeline: an ID like `007` can become the number 7, and a column
# MAGIC that is empty in the first rows can be guessed as text.
# MAGIC
# MAGIC **Predict before you run:** what type will `attended` get, given that future bookings have no value yet?

# COMMAND ----------
# WHAT: previews five rows of bookings.csv, letting Databricks guess the column types.
# LOOK FOR: the column types in the result header. Compare them with the explicit schema in the next cell.
display(A8.sql("""SELECT * FROM read_files('{volume_path}/bookings.csv',
format => 'csv', header => true, inferSchema => true) LIMIT 5"""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Create Delta tables with a schema contract (10 minutes)
# MAGIC Now we load each file into a Delta table with an **explicit schema**: we state every column's type instead of guessing.
# MAGIC `mode => 'FAILFAST'` stops the load if any row does not fit, rather than silently writing nulls.
# MAGIC
# MAGIC **CTAS** (CREATE TABLE AS SELECT) turns a query result into a table in one step.
# MAGIC `CREATE OR REPLACE` means a rerun **resets** these tables to the original data; it does not append duplicates.
# MAGIC
# MAGIC Notice `attended BOOLEAN`: NULL means *no outcome yet*, which is different from `false` (a no-show).

# COMMAND ----------
# WHAT: loads each CSV into its own Delta table using a stated schema, and shows each SQL statement.
# LOOK FOR: three CREATE OR REPLACE TABLE statements. Read one: which part is the schema and which the source file?
schemas = {  # column name and type for each file, in file order
    "events": """event_id STRING, event_name STRING, topic STRING, format STRING,
city STRING, venue STRING, event_date DATE, start_hour INT, capacity INT,
price_gbp INT, status STRING""",
    "bookings": """booking_id STRING, event_id STRING, customer_name STRING,
customer_email STRING, organisation_type STRING, booked_date DATE, ticket_type STRING,
tickets INT, status STRING, attended BOOLEAN""",
    "feedback": """feedback_id STRING, event_id STRING, booking_id STRING,
submitted_date DATE, rating INT, comment STRING""",
}
for key, schema in schemas.items():
    A8.guard(key)
    columns = ", ".join(field.strip().split()[0] for field in schema.split(","))  # just the column names
    # TBLPROPERTIES are labels on the table; cleanup uses them to confirm a table is course work.
    A8.run(f"""CREATE OR REPLACE TABLE {{{key}}} USING DELTA
COMMENT 'a8-databricks-learning synthetic {key}'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')
AS SELECT {columns} FROM read_files('{{volume_path}}/{key}.csv',
format => 'csv', header => true, schema => '{schema}', mode => 'FAILFAST')""")

# COMMAND ----------
# MAGIC %md
# MAGIC The next cell is pure SQL (`%sql`). Session variables such as `a8_events` hold your real table names, and
# MAGIC `IDENTIFIER(...)` lets SQL use a variable as a table name.

# COMMAND ----------
# MAGIC %sql
# MAGIC -- WHAT: counts rows in each new table.
# MAGIC -- LOOK FOR: 60 events, 4,204 bookings and 395 feedback rows.
# MAGIC SELECT 'events' AS dataset, count(*) AS rows FROM IDENTIFIER(a8_events)
# MAGIC UNION ALL SELECT 'bookings', count(*) FROM IDENTIFIER(a8_bookings)
# MAGIC UNION ALL SELECT 'feedback', count(*) FROM IDENTIFIER(a8_feedback);

# COMMAND ----------
# WHAT: checks the row counts, and that every booking points at an event that exists.
# LOOK FOR: "Counts and booking→event referential integrity passed." An AssertionError means the load is wrong.
assert spark.table(A8.t("events")).count() == 60
assert spark.table(A8.t("bookings")).count() == 4204
assert spark.table(A8.t("feedback")).count() == 395
# LEFT ANTI JOIN returns bookings with no matching event. There should be none.
assert A8.sql("""SELECT count(*) FROM {bookings} b LEFT ANTI JOIN {events} e
ON b.event_id = e.event_id""").first()[0] == 0
print("Counts and booking→event referential integrity passed.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Answer an operational question (15 minutes)
# MAGIC "Which events need more bookings?" Two traps:
# MAGIC - a booking can hold several **tickets**, so count tickets, not bookings
# MAGIC - a **cancelled** booking must not occupy a seat
# MAGIC
# MAGIC A **view** stores the query, not a copy of the result. Every read runs it again on the current tables.
# MAGIC
# MAGIC **Predict before you run:** the confirmed-status filter is in the `JOIN ... ON`, not in a `WHERE`. What would
# MAGIC happen to an event with no confirmed bookings if it were in `WHERE`?
# MAGIC *(It would vanish from the result, because WHERE runs after the LEFT JOIN and drops its empty rows.)*

# COMMAND ----------
# WHAT: creates a view of booked and available seats per event, then shows scheduled events.
# LOOK FOR: the view's SQL, then scheduled events sorted by most seats available.
A8.guard("event_availability")
A8.run("""CREATE OR REPLACE VIEW {event_availability}
COMMENT 'a8-databricks-learning current confirmed ticket availability'
AS SELECT e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity,
coalesce(sum(b.tickets), 0) AS booked,
e.capacity - coalesce(sum(b.tickets), 0) AS available
FROM {events} e LEFT JOIN {bookings} b
ON e.event_id = b.event_id AND b.status = 'confirmed'
GROUP BY e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity""")
display(A8.sql("SELECT * FROM {event_availability} WHERE status = 'scheduled' ORDER BY available DESC"))

# COMMAND ----------
# MAGIC %md
# MAGIC The same question can be asked in **PySpark**, Spark's Python API. It runs on the same engine and reads
# MAGIC the same governed table; pick whichever language suits the task.

# COMMAND ----------
# WHAT: counts completed events per city using PySpark instead of SQL.
# LOOK FOR: one row per city. Compare with exercise 1.1 below, which asks for the same thing in SQL.
from pyspark.sql import functions as F

by_city = (spark.table(A8.t("events"))           # read the Delta table, not the CSV
           .where(F.col("status") == "completed")  # keep past events only
           .groupBy("city")
           .agg(F.count("*").alias("events"))
           .orderBy("city"))
display(by_city)

# COMMAND ----------
# MAGIC %md
# MAGIC ### Your turn: change, then transfer
# MAGIC 1. In the PySpark cell, change `completed` to `scheduled`. **Predict** how the result changes, then run it.
# MAGIC 2. Exercise 1.1: write the SQL version of the completed-events-by-city query.
# MAGIC 3. Exercise 1.2: total confirmed **tickets** for each scheduled event. Counting rows is deliberately wrong here.
# MAGIC
# MAGIC Put your SQL between the triple quotes and run the cell. You can use placeholders such as `{events}`.
# MAGIC A blank answer shows the task and a hint. `A8.solution("1.2")` shows a worked answer.

# COMMAND ----------
# WHAT: checks your answer to 1.1 against the course solution, run on your tables.
answer_1_1 = """"""
A8.check("1.1", answer_1_1)

# COMMAND ----------
# WHAT: checks your answer to 1.2.
answer_1_2 = """"""
A8.check("1.2", answer_1_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Delta history is evidence, not a backup (10 minutes)
# MAGIC Every change to a Delta table creates a new **version** in its transaction log. You can read an old version
# MAGIC (**time travel**) and see who changed what (**history**).
# MAGIC Old versions are kept only until files are cleaned up (`VACUUM`), so history is not long-term backup.
# MAGIC
# MAGIC The next cell adds 1 to one event's capacity, reads the old version to prove it is still there, then sets
# MAGIC the value back. It starts from the current value, so running it twice does not drift.

# COMMAND ----------
# WHAT: makes a small change, reads the table as it was before, then restores the value. Finally shows history.
# LOOK FOR: the old capacity from VERSION AS OF, then two UPDATE rows at the top of the history table.
version = A8.sql("DESCRIBE HISTORY {events}").first()["version"]  # newest version number
before = A8.sql("SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0]
try:
    A8.run("UPDATE {events} SET capacity = capacity + 1 WHERE event_id = 'E149'")
    # Time travel: read the table as it was at the earlier version.
    display(A8.sql(f"SELECT event_id, capacity FROM {{events}} VERSION AS OF {version} WHERE event_id = 'E149'"))
    assert A8.sql("SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0] == before + 1
finally:
    A8.run(f"UPDATE {{events}} SET capacity = {before} WHERE event_id = 'E149'")  # always put it back
display(A8.sql("DESCRIBE HISTORY {events}"))
A8.links(("Events: schema, sample and history", "table", "events"),
         ("Availability: upstream lineage", "table", "event_availability"))

# COMMAND ----------
# MAGIC %md
# MAGIC **Do it in the UI**
# MAGIC 1. Open **Events** from the link above → **History**. Find the two UPDATE operations.
# MAGIC 2. Open the availability view → **Lineage**, and expand its upstream tables. Lineage can take a few minutes to appear.
# MAGIC 3. In the **SQL editor**, paste the SELECT printed below, choose a warehouse and run it. Session variables do not
# MAGIC    carry over to the SQL editor, so the printed statement uses your real names.
# MAGIC 4. On the PySpark city result, click **+** → **Visualization** → bar chart, city on X, events on Y.
# MAGIC
# MAGIC **Recap: explain in your own words**
# MAGIC - Why can you stop compute without losing tables?
# MAGIC - Why does a view show new bookings without being recreated?
# MAGIC - What would go wrong if `attended IS NULL` were treated as `false` when training a model?
# MAGIC
# MAGIC **Next:** control who can see what, before using the data to predict attendance.

# COMMAND ----------
# WHAT: prints a ready-to-paste query with your real names, and summarises the module.
A8.code(A8.fmt("SELECT * FROM {event_availability} ORDER BY available DESC"))
A8.next_step(["Governed CSV volume", "Three typed Delta tables", "Availability view",
              "SQL/PySpark queries, a time-travel read and UI lineage inspection"],
             "02_governance", "Control who can see what")
