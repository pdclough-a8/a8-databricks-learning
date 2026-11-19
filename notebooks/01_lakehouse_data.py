# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1. Files to trusted lakehouse data
# MAGIC **Outcome:** three Delta tables, a reusable availability view and evidence of their history and lineage.
# MAGIC **60 minutes:** orient 5 · files 10 · Delta 15 · SQL/PySpark 15 · history/UI 10 · recap 5.
# MAGIC Run `00_setup` first. This lesson writes only your tag's volume, tables and view in the saved schema.
# MAGIC Compute and storage may incur charges. No endpoint, pipeline or app is started.
# MAGIC
# MAGIC ## 1. A lakehouse has separate storage, governance and compute
# MAGIC A **volume** holds files, including CSV, PDFs and images. A **Delta table** adds a transaction log,
# MAGIC schema and SQL access to structured data. **Unity Catalog** governs both.
# MAGIC Your notebook and SQL warehouse are two compute clients of the same persistent objects.
# MAGIC Today the source is synthetic A8 Events data, frozen at **20 November 2026**, not today's clock.

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""))
print("Source files:", [p.name for p in (ROOT / "data" / "raw").glob("*.csv")])

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Land files in a governed volume (10 minutes)
# MAGIC Read the SQL below: the three-part name is your volume, not a table.
# MAGIC `IF NOT EXISTS` makes repeated runs non-duplicating. We check collisions before reusing objects.
# MAGIC `shutil.copyfile` moves local workspace CSV bytes into UC storage, not a database insert.
# MAGIC
# MAGIC **UI alternative:** Catalog → your schema → **Create volume**, managed volume, using the printed name.
# MAGIC Add the comment shown below, then upload all three files from `data/raw`. Do not upload real customer data.
# MAGIC If you use this route, skip the copy cell and continue at `read_files`.

# COMMAND ----------
import shutil
from a8learn import COURSE_ID

A8.guard("raw")
A8.run("""CREATE VOLUME IF NOT EXISTS {raw}
COMMENT 'a8-databricks-learning managed teaching files'""")
for filename in ["events.csv", "bookings.csv", "feedback.csv"]:
    shutil.copyfile(ROOT / "data" / "raw" / filename, Path(A8.volume_path) / filename)
display(dbutils.fs.ls(A8.volume_path))
A8.links(("Raw files, inspect the CSV preview", "volume", "raw"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Inspect before you ingest (5 minutes)
# MAGIC `read_files` reads external bytes. Inference is convenient for exploration but is not a production contract:
# MAGIC identifiers may look numeric and an empty Boolean column may look like text. Inspect the schema and sample.
# MAGIC Our explicit schemas in the next cell avoid that ambiguity.

# COMMAND ----------
display(A8.sql("""SELECT * FROM read_files('{volume_path}/bookings.csv',
format => 'csv', header => true, inferSchema => true) LIMIT 5"""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Create Delta tables with a schema contract (10 minutes)
# MAGIC These are full **replace** operations, not appends. Rerunning resets these three teaching tables to the fixture.
# MAGIC `CTAS` means CREATE TABLE AS SELECT: the query result becomes a transactional table.
# MAGIC Helpers only resolve names and display SQL; the Databricks operations are written here.
# MAGIC Check the type of `attended`: NULL means no known outcome, not a no-show.

# COMMAND ----------
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
for key, schema in schemas.items():
    A8.guard(key)
    columns = ", ".join(field.strip().split()[0] for field in schema.split(","))
    A8.run(f"""CREATE OR REPLACE TABLE {{{key}}} USING DELTA
COMMENT 'a8-databricks-learning synthetic {key}'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}')
AS SELECT {columns} FROM read_files('{{volume_path}}/{key}.csv',
format => 'csv', header => true, schema => '{schema}', mode => 'FAILFAST')""")

# COMMAND ----------
# MAGIC %sql
# MAGIC SELECT 'events' AS dataset, count(*) AS rows FROM IDENTIFIER(a8_events)
# MAGIC UNION ALL SELECT 'bookings', count(*) FROM IDENTIFIER(a8_bookings)
# MAGIC UNION ALL SELECT 'feedback', count(*) FROM IDENTIFIER(a8_feedback);

# COMMAND ----------
# Native SQL notebook cells use variables re-declared by _config in this session.
assert spark.table(A8.t("events")).count() == 60
assert spark.table(A8.t("bookings")).count() == 4204
assert spark.table(A8.t("feedback")).count() == 395
assert A8.sql("""SELECT count(*) FROM {bookings} b LEFT ANTI JOIN {events} e
ON b.event_id = e.event_id""").first()[0] == 0
print("Counts and booking→event referential integrity passed.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Answer an operational question (15 minutes)
# MAGIC "Which events need more bookings?" A booking is not a ticket and a cancellation must not occupy a seat.
# MAGIC Read this view definition aloud. Why is the booking status in the JOIN rather than WHERE?
# MAGIC (A WHERE filter would remove events with no confirmed bookings from a LEFT JOIN.)
# MAGIC A normal view stores a query, not a copied result; downstream reads see the current source tables.

# COMMAND ----------
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
from pyspark.sql import functions as F

# Same engine and governed data, a different API. No CSV re-read.
by_city = (spark.table(A8.t("events")).where(F.col("status") == "completed")
           .groupBy("city").agg(F.count("*").alias("events")).orderBy("city"))
display(by_city)

# COMMAND ----------
# MAGIC %md
# MAGIC ### Your turn, change then transfer
# MAGIC 1. Change the PySpark filter to `scheduled`. Explain the difference without running it first.
# MAGIC 2. Complete 1.1 in SQL. Then solve 1.2, where counting rows is deliberately wrong.
# MAGIC Put SQL between the triple quotes; run again. A blank answer gives a hint, not a notebook failure.
# MAGIC `A8.solution("1.2")` reveals a worked answer. The checker compares results against these tables.

# COMMAND ----------
answer_1_1 = """"""
A8.check("1.1", answer_1_1)

# COMMAND ----------
answer_1_2 = """"""
A8.check("1.2", answer_1_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Delta history is evidence, not an undo button for everything (10 minutes)
# MAGIC Capture a version, make a small reversible update, read that old version, then restore the changed value.
# MAGIC Time travel depends on retained log/data files. Do not VACUUM this course; history is not long-term backup.
# MAGIC This demonstration always starts from the **current** value, so rerunning does not subtract capacity repeatedly.

# COMMAND ----------
version = A8.sql("DESCRIBE HISTORY {events}").first()["version"]
before = A8.sql("SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0]
try:
    A8.run("UPDATE {events} SET capacity = capacity + 1 WHERE event_id = 'E149'")
    display(A8.sql(f"SELECT event_id, capacity FROM {{events}} VERSION AS OF {version} WHERE event_id = 'E149'"))
    assert A8.sql("SELECT capacity FROM {events} WHERE event_id = 'E149'").first()[0] == before + 1
finally:
    A8.run(f"UPDATE {{events}} SET capacity = {before} WHERE event_id = 'E149'")
display(A8.sql("DESCRIBE HISTORY {events}"))
A8.links(("Events: schema, sample and history", "table", "events"),
         ("Availability: upstream lineage", "table", "event_availability"))

# COMMAND ----------
# MAGIC %md
# MAGIC **Do it in the UI:** open Events → **History** (or Details/History in your UI) and inspect UPDATE operations.
# MAGIC Open the view → **Lineage** and expand upstream tables. Lineage may take time to appear.
# MAGIC In SQL editor, paste the printed fully qualified SELECT, choose your warehouse and compare the result.
# MAGIC Notebook session variables do not carry over to the SQL editor; use the real name printed below.
# MAGIC Add a chart from the city result: bar chart, city on X, events on Y. Save the notebook with your chart.
# MAGIC
# MAGIC **Explain:** Why can you stop compute without losing tables? Why can a view change without being rewritten?
# MAGIC What would go wrong if `attended IS NULL` were treated as `false` in training?
# MAGIC **Next:** govern a copy before using data to predict attendance.

# COMMAND ----------
A8.code(A8.fmt("SELECT * FROM {event_availability} ORDER BY available DESC"))
A8.next_step(["Governed CSV volume", "Three typed Delta tables", "Availability view",
              "SQL/PySpark queries, a time-travel read and UI lineage inspection"],
             "02_governance", "Control who can see what")
