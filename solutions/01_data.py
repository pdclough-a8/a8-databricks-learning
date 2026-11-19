# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | Lesson 1 solution
# MAGIC Try the task first. This solution uses the same configured, marked table.

# COMMAND ----------
# MAGIC %run ../notebooks/00_start_here

# COMMAND ----------
display(spark.sql(
    f"SELECT event_id, capacity - booked AS remaining FROM {TABLE} "
    "WHERE city = 'Manchester' AND capacity - booked < 10 ORDER BY event_id"
))
# Expect one row: E102, 3. This is availability, not an attendance prediction.
