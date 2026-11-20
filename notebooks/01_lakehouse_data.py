# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1. Files to trusted lakehouse data
# MAGIC **Where this sits:** the data foundation for descriptive analytics in Module 1b and prediction in Module 3.
# MAGIC
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
# MAGIC | `IDENTIFIER(a8_events)` in SQL | uses a session variable containing your real table name |
# MAGIC | `spark.sql(sql, args={...})` | runs standard SQL; parameters carry values such as file paths |
# MAGIC | `A8.t("events")` | returns your real table name, for Python APIs such as `spark.table(...)` |
# MAGIC | `A8.guard("events")` | a safety check: stops if the object exists but is not yours |
# MAGIC | `A8.links(...)` | shows links that open the matching page in the Databricks UI |
# MAGIC | `A8.check("1.1", answer)` | checks your exercise answer against your own tables |
# MAGIC
# MAGIC In Python we resolve names once with `A8.t` and interpolate those validated names into f-strings.
# MAGIC Values use `spark.sql(..., args={...})` parameters. Saved views use real names because their definitions
# MAGIC cannot contain session variables or parameters. Everything else is ordinary Databricks SQL, PySpark or Python.

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; these are standard Python and PySpark libraries.
import shutil
from pathlib import Path

from a8learn import COURSE_ID
from pyspark.sql import functions as F

# COMMAND ----------
# WHAT: resolves your validated object names for Python SQL and DataFrame APIs.
# LOOK FOR: no output; later sections reuse these names and the volume path.
events = A8.t("events")
bookings = A8.t("bookings")
feedback = A8.t("feedback")
raw = A8.t("raw")
event_availability = A8.t("event_availability")
volume_path = A8.volume_path
tables = {"events": events, "bookings": bookings, "feedback": feedback}

# COMMAND ----------
# WHAT: opens links to your schema and the SQL editor.
# LOOK FOR: links to your own namespace.
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""))

# COMMAND ----------
# WHAT: lists the CSV files shipped with the course.
# LOOK FOR: bookings.csv, events.csv and feedback.csv.
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
# MAGIC Upload the three files from `data/raw`, then skip the create-volume and copy-files cells. Run the listing
# MAGIC cell to inspect your upload. Never upload real customer data.

# COMMAND ----------

# WHAT: creates your governed volume if needed.
# LOOK FOR: a successful CREATE VOLUME; an existing owned volume is kept.
A8.guard("raw")
spark.sql(f"""CREATE VOLUME IF NOT EXISTS {raw}
COMMENT 'a8-databricks-learning managed teaching files'""")

# COMMAND ----------
# WHAT: copies the source CSV files into the volume.
# LOOK FOR: no output; a rerun overwrites the same three fixture files.
A8.guard("raw")
for filename in ["events.csv", "bookings.csv", "feedback.csv"]:
    # Volumes expose a filesystem path, so ordinary file copying works.
    shutil.copyfile(ROOT / "data" / "raw" / filename, Path(volume_path) / filename)

# COMMAND ----------
# WHAT: shows the files now governed by Unity Catalog.
# LOOK FOR: three files with sizes, and a link to inspect their CSV preview.
display(dbutils.fs.ls(volume_path))
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

# WHAT: previews five bookings with inferred types.
# LOOK FOR: the result header's types; compare them with the explicit schema below.
display(spark.sql("""SELECT * FROM read_files(:path,
format => 'csv', header => true, inferSchema => true) LIMIT 5""",
                  args={"path": f"{volume_path}/bookings.csv"}))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Create Delta tables with a schema contract (10 minutes)
# MAGIC Now we load each file into a Delta table with an **explicit schema**: we state every column's type instead of
# MAGIC guessing.
# MAGIC `mode => 'FAILFAST'` stops the load if any row does not fit, rather than silently writing nulls.
# MAGIC
# MAGIC **CTAS** (CREATE TABLE AS SELECT) turns a query result into a table in one step.
# MAGIC `CREATE OR REPLACE` means a rerun **resets** these tables to the original data; it does not append duplicates.
# MAGIC
# MAGIC Notice `attended BOOLEAN`: NULL means *no outcome yet*, which is different from `false` (a no-show).
# MAGIC We bind the file paths and schemas in SELECT queries first, naming them with **temporary views** that last only
# MAGIC for this notebook session. CTAS then reads those views. This also works on Runtime 16.4 LTS, where parameter
# MAGIC markers cannot appear directly in DDL statements such as CREATE TABLE.
# MAGIC The temporary views are removed afterwards.

# COMMAND ----------

# WHAT: states the column contract for each CSV.
# LOOK FOR: explicit types, including BOOLEAN attendance and DATE columns.
schemas = {
    "events": """event_id STRING, event_name STRING, topic STRING, format STRING,
city STRING, venue STRING, event_date DATE, start_hour INT, capacity INT,
price_gbp INT, status STRING""",
    "bookings": """booking_id STRING, event_id STRING, customer_name STRING,
customer_email STRING, organisation_type STRING, booked_date DATE, ticket_type STRING,
tickets INT, status STRING, attended BOOLEAN""",
    "feedback": """feedback_id STRING, event_id STRING, booking_id STRING,
submitted_date DATE, rating INT, comment STRING""",
}

# COMMAND ----------
# WHAT: prepares typed CSV queries as session-only source views.
# LOOK FOR: no output; the explicit projection excludes any rescued-data metadata column.
for key, schema in schemas.items():
    columns = ", ".join(field.strip().split()[0] for field in schema.split(","))
    source = spark.sql(f"""SELECT {columns} FROM read_files(:path,
format => 'csv', header => true, schema => :schema, mode => 'FAILFAST')""",
                       args={"path": f"{volume_path}/{key}.csv", "schema": schema})
    source.createOrReplaceTempView(f"a8_source_{key}")

# COMMAND ----------
# WHAT: loads the typed CSV queries into owned Delta tables with CTAS.
# LOOK FOR: three CREATE OR REPLACE TABLE statements; reruns reset the same tables without appending.
for key, table in tables.items():
    A8.guard(key)
    # Ownership labels let cleanup distinguish course work from unrelated tables.
    statement = f"""CREATE OR REPLACE TABLE {table} USING DELTA
COMMENT 'a8-databricks-learning synthetic {key}'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')
AS SELECT * FROM a8_source_{key}"""
    print(statement)
    spark.sql(statement)

# COMMAND ----------
# WHAT: removes the session-only source views after ingestion.
# LOOK FOR: no output; the persisted Delta tables are unaffected.
for key in tables:
    spark.catalog.dropTempView(f"a8_source_{key}")

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

# WHAT: Check: verifies the three fixture row counts.
# LOOK FOR: a clear pass message for each expected count.
A8.expect(spark.table(events).count() == 60, "Events must contain 60 rows.")
A8.expect(spark.table(bookings).count() == 4204, "Bookings must contain 4,204 rows.")
A8.expect(spark.table(feedback).count() == 395, "Feedback must contain 395 rows.")

# COMMAND ----------
# WHAT: Check: verifies every booking points at an existing event.
# LOOK FOR: zero unmatched bookings and a pass message.
# LEFT ANTI JOIN returns bookings with no matching event.
orphan_count = spark.sql(f"""SELECT count(*) FROM {bookings} b LEFT ANTI JOIN {events} e
ON b.event_id = e.event_id""").first()[0]
A8.expect(orphan_count == 0, "Every booking must reference an existing event.")

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

# WHAT: saves a reusable query for booked and available seats.
# LOOK FOR: a view created with real table names, not session variables.
A8.guard("event_availability")
# Saved views cannot contain session variables or parameter markers.
spark.sql(f"""CREATE OR REPLACE VIEW {event_availability}
COMMENT 'a8-databricks-learning current confirmed ticket availability'
AS SELECT e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity,
coalesce(sum(b.tickets), 0) AS booked,
e.capacity - coalesce(sum(b.tickets), 0) AS available
FROM {events} e LEFT JOIN {bookings} b
ON e.event_id = b.event_id AND b.status = 'confirmed'
GROUP BY e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity""")

# COMMAND ----------
# WHAT: shows scheduled events with the most available seats first.
# LOOK FOR: the live result of the saved availability view.
display(spark.sql(f"SELECT * FROM {event_availability} WHERE status = 'scheduled' ORDER BY available DESC"))

# COMMAND ----------
# MAGIC %md
# MAGIC The same question can be asked in **PySpark**, Spark's Python API. It runs on the same engine and reads
# MAGIC the same governed table; pick whichever language suits the task.

# COMMAND ----------

# WHAT: groups completed events by city using PySpark.
# LOOK FOR: no output yet; by_city is a Spark DataFrame.
by_city = (spark.table(events)
           .where(F.col("status") == "completed")
           .groupBy("city")
           .agg(F.count("*").alias("events"))
           .orderBy("city"))

# COMMAND ----------
# WHAT: shows the PySpark city counts.
# LOOK FOR: one row per city; exercise 1.1 asks for the same result in SQL.
display(by_city)

# COMMAND ----------
# MAGIC %md
# MAGIC ### Your turn: change, then transfer
# MAGIC 1. In the PySpark cell, change `completed` to `scheduled`. **Predict** how the result changes, then run it.
# MAGIC 2. Exercise 1.1: write the SQL version of the completed-events-by-city query.
# MAGIC 3. Exercise 1.2: total confirmed **tickets** for each scheduled event. Counting rows is deliberately wrong here.
# MAGIC
# MAGIC Put your SQL between the triple quotes and run the cell. Use `IDENTIFIER(a8_events)` and
# MAGIC `IDENTIFIER(a8_bookings)` for table names, just as in the `%sql` example.
# MAGIC A blank answer shows the task and a hint. `A8.solution("1.2")` shows a worked answer.

# COMMAND ----------

# WHAT: Check: compares your exercise 1.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, or feedback on your query.
answer_1_1 = """"""
A8.check("1.1", answer_1_1)

# COMMAND ----------

# WHAT: Check: compares your exercise 1.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, or feedback on your query.
answer_1_2 = """"""
A8.check("1.2", answer_1_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Delta history is evidence, not a backup (10 minutes)
# MAGIC Every change to a Delta table creates a new **version** in its transaction log. You can read an old version
# MAGIC (**time travel**) and see who changed what (**history**).
# MAGIC Old versions are kept only until files are cleaned up (`VACUUM`), so history is not long-term backup.
# MAGIC
# MAGIC The next cells capture the current version and capacity, temporarily add 1 to E149's capacity and read
# MAGIC the old version. The update, eager reads (`collect`/`first`) and restore deliberately share one compact
# MAGIC `try/finally` cell: `finally` restores the original value even if a read fails. Splitting that safety block
# MAGIC across cells could strand the changed data if you stopped midway. Display and Check cells run only after
# MAGIC restoration, so even a failed check cannot leave the increment behind. Rerunning the demonstration starts
# MAGIC from the current value and does not drift; rerun the baseline cell to capture a fresh history version.

# COMMAND ----------

# WHAT: captures the current Delta version and capacity before the demonstration.
# LOOK FOR: no output; version and before are the baseline for this run.
A8.guard("events")
version = spark.sql(f"DESCRIBE HISTORY {events}").first()["version"]
before = spark.sql(f"SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0]

# COMMAND ----------
# WHAT: demonstrates a temporary Delta update with guaranteed restoration.
# LOOK FOR: no output; both versions are collected before the finally block restores capacity.
A8.guard("events")
try:
    spark.sql(f"UPDATE {events} SET capacity = :capacity WHERE event_id = 'E149'",
              args={"capacity": before + 1})
    old_rows = spark.sql(
        f"SELECT event_id, capacity FROM {events} VERSION AS OF {version} WHERE event_id = 'E149'"
    ).collect()
    changed = spark.sql(f"SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0]
finally:
    spark.sql(f"UPDATE {events} SET capacity = :capacity WHERE event_id = 'E149'",
              args={"capacity": before})

# COMMAND ----------
# WHAT: shows the old-version rows collected before restoration.
# LOOK FOR: E149's original capacity, not its temporary increment.
display(spark.createDataFrame(old_rows))

# COMMAND ----------
# WHAT: Check: verifies time travel, the temporary update and the restored baseline.
# LOOK FOR: pass messages proving the table has not drifted.
A8.expect(len(old_rows) == 1 and old_rows[0]["capacity"] == before,
          "Time travel must return E149's original capacity.")
A8.expect(changed == before + 1, "The temporary update must add exactly one seat.")
restored = spark.sql(f"SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0]
A8.expect(restored == before, "E149's capacity must be restored before continuing.")

# COMMAND ----------
# WHAT: shows the Delta transaction history.
# LOOK FOR: two UPDATE operations at the top: the change and its restoration.
display(spark.sql(f"DESCRIBE HISTORY {events}"))

# COMMAND ----------
# WHAT: opens the history and lineage pages.
# LOOK FOR: links to Events and its downstream availability view.
A8.links(("Events: schema, sample and history", "table", "events"),
         ("Availability: upstream lineage", "table", "event_availability"))

# COMMAND ----------
# MAGIC %md
# MAGIC **Do it in the UI**
# MAGIC 1. Open **Events** from the link above → **History**. Find the two UPDATE operations.
# MAGIC 2. Open the availability view → **Lineage**, and expand its upstream tables. Lineage can take a few minutes to
# MAGIC   appear.
# MAGIC 3. In the **SQL editor**, paste the SELECT printed below, choose a warehouse and run it. Session variables
# MAGIC    do not carry over to the SQL editor, so the printed statement uses your real names.
# MAGIC 4. On the PySpark city result, click **+** → **Visualization** → bar chart, city on X, events on Y.
# MAGIC
# MAGIC **Recap: explain in your own words**
# MAGIC - Why can you stop compute without losing tables?
# MAGIC - Why does a view show new bookings without being recreated?
# MAGIC - What would go wrong if `attended IS NULL` were treated as `false` when training a model?
# MAGIC
# MAGIC **Next:** describe the business with a dashboard and check Genie answers, then enforce data access in Module 2.

# COMMAND ----------

# WHAT: prints a query ready to paste into the SQL editor.
# LOOK FOR: your real availability view name.
print(f"SELECT * FROM {event_availability} ORDER BY available DESC")

# COMMAND ----------
# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and your next lesson.
A8.next_step(["Governed CSV volume", "Three typed Delta tables", "Availability view",
              "SQL/PySpark queries, a time-travel read and UI lineage inspection"],
             "01b_descriptive_analytics", "Describe the business with AI/BI and Genie")
