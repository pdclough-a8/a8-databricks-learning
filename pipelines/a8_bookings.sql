-- Databricks notebook source
-- MAGIC %md
-- MAGIC # A8 | Bookings pipeline (used by Module 13)
-- MAGIC A Lakeflow Spark Declarative Pipeline. You declare **what each table is**; Databricks works out the order,
-- MAGIC reads only new files and keeps the tables up to date. Three layers, often called bronze, silver and gold:
-- MAGIC
-- MAGIC | Layer | Table | Holds |
-- MAGIC |---|---|---|
-- MAGIC | Bronze | `${a8_bronze}` | every new booking file exactly as received, plus the file it came from |
-- MAGIC | Silver | `${a8_silver}` | only the rows that pass the data-quality rules |
-- MAGIC | Gold | `${a8_gold}` | seats booked and seats available for every event, old and new bookings together |
-- MAGIC
-- MAGIC The `${...}` names are **pipeline settings** that Module 13 fills in with your learner tag, so your tables
-- MAGIC never collide with anyone else's. Do not run this file as a notebook; Module 13 creates the pipeline for you.

-- COMMAND ----------

-- Bronze: a streaming table. It reads each new file in the folder once, however many times the pipeline runs.
CREATE OR REFRESH STREAMING TABLE ${a8_bronze}
COMMENT 'a8-databricks-learning new booking files as received'
AS SELECT *, _metadata.file_path AS source_file
FROM STREAM read_files(
  '${a8_incoming}',
  format => 'csv',
  header => true,
  schema => 'booking_id STRING, event_id STRING, customer_name STRING, customer_email STRING,
             organisation_type STRING, booked_date DATE, ticket_type STRING, tickets INT, status STRING,
             attended BOOLEAN');

-- COMMAND ----------

-- Silver: each constraint is a data-quality rule. A row that breaks one is dropped, and the pipeline counts it.
CREATE OR REFRESH STREAMING TABLE ${a8_silver} (
  CONSTRAINT booking_id_present EXPECT (booking_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT tickets_positive EXPECT (tickets > 0) ON VIOLATION DROP ROW,
  CONSTRAINT status_known EXPECT (status IN ('confirmed', 'cancelled')) ON VIOLATION DROP ROW
)
COMMENT 'a8-databricks-learning new bookings that passed the data-quality rules'
AS SELECT booking_id, event_id, customer_name, customer_email, organisation_type, booked_date, ticket_type,
          tickets, status
FROM STREAM(${a8_bronze});

-- COMMAND ----------

-- Gold: a materialized view, a stored query result the pipeline refreshes. It adds the new confirmed tickets to the
-- history already in your bookings table, so seats left reflect bookings made after 20 November 2026.
CREATE OR REFRESH MATERIALIZED VIEW ${a8_gold}
COMMENT 'a8-databricks-learning live seats booked and available per event'
AS SELECT e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity,
          coalesce(sum(b.tickets), 0) AS booked,
          e.capacity - coalesce(sum(b.tickets), 0) AS available
FROM ${a8_events} e
LEFT JOIN (
  SELECT event_id, tickets FROM ${a8_bookings} WHERE status = 'confirmed'
  UNION ALL
  SELECT event_id, tickets FROM ${a8_silver} WHERE status = 'confirmed'
) b ON e.event_id = b.event_id
GROUP BY e.event_id, e.event_name, e.city, e.event_date, e.status, e.capacity;
