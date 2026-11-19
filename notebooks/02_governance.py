# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 2. Control who can see what
# MAGIC **Outcome:** a documented, tagged table with a real row filter and email mask, plus an explanation of its limits.
# MAGIC **60 minutes:** permissions 10 · metadata 10 · policies 20 · exercises 10 · audit/lineage 10.
# MAGIC Uses Module 1 tables. Writes a **separate governed copy** and two SQL functions. No group creation or grants.
# MAGIC The simple demo policy affects everyone equally; it does not pretend to prove multi-user role separation.
# MAGIC
# MAGIC ## 1. Three different questions
# MAGIC **Discovery:** can I find it? **Authorisation:** may I SELECT it? **Policy:** which rows and values do I see?
# MAGIC A catalog/schema grants USE; a table grants SELECT. Owning a notebook does not confer data privileges.
# MAGIC A filter in a notebook can be removed by a reader; a UC table policy is enforced by the data platform.

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
A8.require("events", "bookings")
A8.links(("Schema permissions", "schema", ""), ("Source bookings", "table", "bookings"))
display(A8.sql("SHOW GRANTS ON TABLE {bookings}"))
display(A8.sql("SELECT current_user() AS querying_identity"))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** open Bookings → **Permissions**. Identify the owner and inherited privileges.
# MAGIC Do not grant `ALL PRIVILEGES` to make an exercise work.
# MAGIC In a real team an admin would grant USE CATALOG, USE SCHEMA and SELECT to an existing account group.
# MAGIC A table grant alone is insufficient without USE on both parents.
# MAGIC
# MAGIC **Read-only example, do not execute here:**
# MAGIC ```sql
# MAGIC GRANT SELECT ON TABLE catalog.schema.table TO `approved_analyst_group`;
# MAGIC ```
# MAGIC An app's service principal needs its own permissions, not your notebook's identity.

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Create a clearly labelled policy sandbox (10 minutes)
# MAGIC Join city into a copy so that a row filter can use a column on the same table.
# MAGIC Never attach experimental policies to the source needed by later lessons.
# MAGIC On rerun, keep an existing copy and policies rather than replacing a policy-protected table.
# MAGIC This makes an interrupted run resumable. To refresh the copy, clean it up explicitly first.

# COMMAND ----------
A8.guard("bookings_governed")
if not A8.exists("bookings_governed"):
    A8.run("""CREATE TABLE {bookings_governed} USING DELTA
COMMENT 'a8-databricks-learning synthetic contacts: demonstration policies only'
AS SELECT b.*, e.city FROM {bookings} b JOIN {events} e USING (event_id)""")
A8.run("""ALTER TABLE {bookings_governed} SET TAGS ('a8_data_class' = 'synthetic_contact',
'a8_purpose' = 'learning')""")
display(A8.sql("DESCRIBE TABLE EXTENDED {bookings_governed}"))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI alternative:** open the copy → Overview/Details, edit its comment and add the same two tags.
# MAGIC These are **ordinary descriptive tags**, not governed tags and not access controls.
# MAGIC Do not label synthetic contacts as real PII. In production a comment should describe owner, meaning,
# MAGIC freshness and intended use without including confidential values.
# MAGIC
# MAGIC ## 3. Mask values, filter rows (20 minutes)
# MAGIC A SQL UDF is a named expression. A column mask returns the column's type; a row filter returns Boolean.
# MAGIC First test each function by calling it; then attach it with ALTER TABLE.
# MAGIC Here **all users** see only Leeds/Online and masked emails, including the table owner.
# MAGIC This is deliberate so you can observe enforcement as a solo learner.
# MAGIC Production policies usually use `is_account_group_member('approved_group')` and an entitlement mapping table.
# MAGIC Do not invent a privileged group or copy this city's rule into production.

# COMMAND ----------
for key in ["mask_email", "city_filter"]:
    A8.guard(key)
A8.run("""CREATE OR REPLACE FUNCTION {mask_email}(email STRING)
RETURNS STRING COMMENT 'a8-databricks-learning demo mask for every reader'
RETURN CASE WHEN email IS NULL THEN NULL
ELSE concat(left(email, 1), '***@example.com') END""")
A8.run("""CREATE OR REPLACE FUNCTION {city_filter}(city STRING)
RETURNS BOOLEAN COMMENT 'a8-databricks-learning demo cities for every reader'
RETURN city IN ('Leeds', 'Online')""")
display(A8.sql("""SELECT {mask_email}('fictional@example.com') AS masked,
{city_filter}('Leeds') AS leeds_allowed, {city_filter}('London') AS london_allowed"""))

# COMMAND ----------
A8.run("ALTER TABLE {bookings_governed} ALTER COLUMN customer_email SET MASK {mask_email}")
A8.run("ALTER TABLE {bookings_governed} SET ROW FILTER {city_filter} ON (city)")
display(A8.sql("SELECT booking_id, city, customer_email FROM {bookings_governed} LIMIT 10"))

# COMMAND ----------
# Independent assertions test the intended policy, not the checker solution alone.
governed = A8.sql("SELECT DISTINCT city FROM {bookings_governed}").collect()
assert {r[0] for r in governed} == {"Leeds", "Online"}
assert A8.sql("SELECT count(*) FROM {bookings_governed} WHERE customer_email NOT LIKE '%***%'").first()[0] == 0
assert A8.sql("SELECT count(*) FROM {bookings} WHERE customer_email LIKE '%***%'").first()[0] == 0
assert A8.sql("SELECT count(*) FROM {bookings_governed}").first()[0] < spark.table(A8.t("bookings")).count()
print("Policy enforcement observed; source data unchanged.")
A8.links(("Governed copy: inspect mask and row filter", "table", "bookings_governed"),
         ("SQL mask definition", "function", "mask_email"))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** find the mask indicator beside `customer_email` and the Row filter on the table Overview.
# MAGIC Inspect the named UDF. Query the table in SQL editor using its fully qualified name; the policy still applies.
# MAGIC **UI alternative to attachment:** create the functions above, then Table → Row filter → Add;
# MAGIC choose `city_filter` with `city`. On the email column choose Mask → `mask_email`.
# MAGIC
# MAGIC **Think critically:** the table still exposes `customer_name`. A partial email mask does not anonymise a person.
# MAGIC You own the source table too, so you can read its unmasked data. This proves policy execution on this copy,
# MAGIC not protection from a malicious owner. A real analyst must not also have access to the unrestricted source.

# COMMAND ----------
answer_2_1 = """"""
A8.check("2.1", answer_2_1)

# COMMAND ----------
answer_2_2 = """"""
A8.check("2.2", answer_2_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Trace and audit (10 minutes)
# MAGIC **Lineage** answers "where did this data come from?" **Audit** answers "who did what, when?"
# MAGIC Neither proves the data is correct. In the governed table's Lineage tab expand Bookings and Events.
# MAGIC The platform captures lineage from supported queries, not arbitrary Python transformations on your laptop.
# MAGIC
# MAGIC System tables may be unavailable or restricted, particularly in Free Edition. The optional cell below
# MAGIC reads only recent matching objects for your identity. A permission error is a recorded limitation,
# MAGIC not a reason to request broad admin access. There may also be an ingestion delay.

# COMMAND ----------
if A8.gate("read_system_evidence", "Try restricted lineage/audit system tables?"):
    from a8learn import sql_string
    for label, query in [
        ("lineage", f"""SELECT event_time, source_table_full_name, target_table_full_name
FROM system.access.table_lineage
WHERE event_date >= date_sub(current_date(), 1)
AND created_by = {sql_string(A8.cfg.user)}
AND target_table_name = {sql_string(A8.name('bookings_governed'))}
ORDER BY event_time DESC LIMIT 10"""),
        ("audit", f"""SELECT event_time, service_name, action_name
FROM system.access.audit WHERE event_date >= date_sub(current_date(), 1)
AND user_identity.email = {sql_string(A8.cfg.user)}
AND to_json(request_params) LIKE '%{A8.name('bookings_governed')}%'
ORDER BY event_time DESC LIMIT 10"""),
    ]:
        try:
            display(spark.sql(query))
        except Exception as error:
            print(f"{label} unavailable ({type(error).__name__}). Use Catalog lineage and ask your admin about availability.")
else:
    print("System tables skipped. Inspect Catalog lineage instead.")

# COMMAND ----------
# MAGIC %md
# MAGIC **Recap, explain before moving on:** Why is a tag not a permission? Why does the policy affect the owner?
# MAGIC What extra evidence would require a second identity? Which source grants would you remove for an analyst?
# MAGIC Policies remain attached for the next visit. Cleanup drops the copy before its UDFs so no dangling reference remains.

# COMMAND ----------
A8.next_step(["A documented/tagged policy sandbox", "Two UC SQL functions",
              "Observed email masking and city filtering", "A distinction between lineage, audit and access grants"],
             "03_predictive_ml", "Predict turnout, track and register a model")
