# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1. Trust the data
# MAGIC **Outcome:** answer an operations question with checked arithmetic.
# MAGIC Start with readiness complete. Read `docs/lessons/01-data.md`; choose one route.
# MAGIC `%run` below shares setup variables with this notebook. Enter widget values here too.

# COMMAND ----------
# MAGIC %run ./00_start_here

# COMMAND ----------
# MAGIC %md
# MAGIC ## Create once, reuse safely
# MAGIC This next cell WRITES one Delta table in your authorised existing schema.
# MAGIC Inspect TABLE and MARKER above. Set the flag to True only when ready.
# MAGIC Reruns check both the marker and exact fixture; they never append or overwrite.
# MAGIC If you used the UI upload route, set the exact comment marker there first.

# COMMAND ----------
CREATE_MY_TABLE = False
if CREATE_MY_TABLE:
    ensure_table(spark, CATALOG, SCHEMA, TAG, EVENTS)
else:
    print("No write. To create your table, review the destination and enable this cell's flag.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Worked example
# MAGIC A table stores rows; a query selects facts for a question.
# MAGIC `remaining` is a calculation, not another source of bookings.
# MAGIC Run only after your table exists. Expect E101=18 and E104=22.

# COMMAND ----------
if not check_table(spark, CATALOG, SCHEMA, TAG, EVENTS):
    raise ValueError("Create your marked table using your chosen route first.")
display(spark.sql(
    f"SELECT event_id, event_name, city, capacity - booked AS remaining "
    f"FROM {TABLE} WHERE city = 'Leeds' ORDER BY event_id"
))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Make one change
# MAGIC Copy the query to a new cell. Change only Leeds to Manchester.
# MAGIC Predict the two IDs and remaining places before running.
# MAGIC ## Complete a gap
# MAGIC Fill `YOUR_PREDICATE` below to show Manchester events with fewer than ten places.
# MAGIC Hint: use `capacity - booked < 10`. Full solution: `solutions/01_data.py`.
# MAGIC ## Transfer
# MAGIC In a new cell find Bristol availability without copying the worked example.
# MAGIC Explain why booked places do not predict future attendance.

# COMMAND ----------
YOUR_PREDICATE = None  # Replace None with a SQL condition string.
if YOUR_PREDICATE is not None:
    display(spark.sql(
        f"SELECT event_id, capacity - booked AS remaining FROM {TABLE} "
        f"WHERE city = 'Manchester' AND ({YOUR_PREDICATE}) ORDER BY event_id"
    ))

# COMMAND ----------
# MAGIC %md
# MAGIC **Check:** Manchester under ten returns only E102, remaining=3. Bristol E105=5.
# MAGIC Save your query and explanation in your own progress note, then go to `02_ask_a_model`.
# MAGIC This table is a learning artefact. The app later uses the same CSV, not this table.
