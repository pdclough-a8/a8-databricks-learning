# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 2. Control who can see what
# MAGIC **By the end of this notebook you will have:**
# MAGIC - read the permissions on your tables
# MAGIC - a documented, tagged copy of the bookings table
# MAGIC - a **row filter** and an **email mask** enforced by Unity Catalog, and evidence that they work
# MAGIC - a clear view of what these controls do **not** protect
# MAGIC
# MAGIC **60 minutes:** permissions 10 · metadata 10 · policies 20 · exercises 10 · lineage and audit 10.
# MAGIC
# MAGIC **Before you start:** run Module 1. This lesson writes a **separate copy** of bookings and two SQL functions.
# MAGIC It creates no groups and grants nothing. The demo policy applies to everyone, including you, so that you can
# MAGIC see it working on your own; it does not prove separation between different users.
# MAGIC
# MAGIC ## 1. Three different questions
# MAGIC | Question | Databricks feature | Example |
# MAGIC |---|---|---|
# MAGIC | **Discovery:** can I find it? | Catalog browsing, comments, tags | You can see the table exists |
# MAGIC | **Authorisation:** may I read it? | Privileges such as `SELECT` | You may query the table |
# MAGIC | **Policy:** which rows and values do I see? | Row filters, column masks | You see only Leeds rows, with emails hidden |
# MAGIC
# MAGIC Privileges are inherited downwards: to read a table you need `USE CATALOG` on its catalog, `USE SCHEMA` on its
# MAGIC schema and `SELECT` on the table. A filter written in a notebook can be deleted by whoever runs it;
# MAGIC a Unity Catalog policy is enforced by the platform on every query, from any tool.

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------
# WHAT: checks Module 1's tables exist, then shows who has which privileges on your bookings table.
# LOOK FOR: a grants table (it may be empty if you hold privileges only as owner), then your own identity.
A8.require("events", "bookings")
A8.links(("Schema permissions", "schema", ""), ("Source bookings", "table", "bookings"))
display(A8.sql("SHOW GRANTS ON TABLE {bookings}"))
display(A8.sql("SELECT current_user() AS querying_identity"))  # policies are evaluated for this identity

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** open Bookings → **Permissions**. Who is the owner? Which privileges are inherited from the schema?
# MAGIC
# MAGIC Do not grant `ALL PRIVILEGES` to make an exercise work. In a real team an admin grants the minimum to an
# MAGIC existing **group**, never to individuals one by one. For example (read only, do not run here):
# MAGIC ```sql
# MAGIC GRANT USE CATALOG ON CATALOG my_catalog TO `approved_analysts`;
# MAGIC GRANT USE SCHEMA ON SCHEMA my_catalog.my_schema TO `approved_analysts`;
# MAGIC GRANT SELECT ON TABLE my_catalog.my_schema.bookings TO `approved_analysts`;
# MAGIC ```
# MAGIC An app later runs as its own **service principal**, which needs its own grants; it does not borrow yours.
# MAGIC
# MAGIC ## 2. Create a clearly labelled policy sandbox (10 minutes)
# MAGIC We attach experimental policies to a **copy**, never to the source tables that later lessons need.
# MAGIC The copy includes `city` from events, because a row filter can only use columns of its own table.
# MAGIC
# MAGIC On a rerun the copy is **kept**, with its policies, rather than replaced. To refresh it, delete it first
# MAGIC with `99_pause_and_cleanup`.

# COMMAND ----------
# WHAT: creates the governed copy (first run only) and adds two descriptive tags.
# LOOK FOR: in the table description, the comment and a Tags section with a8_data_class and a8_purpose.
A8.guard("bookings_governed")
if not A8.exists("bookings_governed"):
    A8.run("""CREATE TABLE {bookings_governed} USING DELTA
COMMENT 'a8-databricks-learning synthetic contacts: demonstration policies only'
AS SELECT b.*, e.city FROM {bookings} b JOIN {events} e USING (event_id)""")
# Tags describe and help people find data. They do not restrict access on their own.
A8.run("""ALTER TABLE {bookings_governed} SET TAGS ('a8_data_class' = 'synthetic_contact',
'a8_purpose' = 'learning')""")
display(A8.sql("DESCRIBE TABLE EXTENDED {bookings_governed}"))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI alternative:** open the copy → **Overview**, edit its comment and add the same two tags.
# MAGIC These are ordinary descriptive tags, not access controls. A good production comment says who owns the data,
# MAGIC what it means, how fresh it is and what it may be used for, without including confidential values.
# MAGIC
# MAGIC ## 3. Mask values and filter rows (20 minutes)
# MAGIC Both policies are **SQL functions** (UDFs) stored in Unity Catalog:
# MAGIC - a **column mask** takes the real value and returns what the reader may see, of the same type
# MAGIC - a **row filter** takes column values and returns `true` (show the row) or `false` (hide it)
# MAGIC
# MAGIC We first create and test each function on its own, then attach it to the table with `ALTER TABLE`.
# MAGIC
# MAGIC In this demo **everyone** sees only Leeds and Online rows, with masked emails, including you as owner.
# MAGIC Real policies decide per reader, for example with `is_account_group_member('approved_analysts')`.
# MAGIC Do not invent a privileged group, and do not copy this city rule into production.
# MAGIC
# MAGIC **Predict before you run:** what will `mask_email('fictional@example.com')` return?

# COMMAND ----------
# WHAT: creates the mask and filter functions, then calls them directly to test them.
# LOOK FOR: masked = f***@example.com, leeds_allowed = true, london_allowed = false.
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
# WHAT: attaches the mask to customer_email and the filter to city, then queries the governed copy.
# LOOK FOR: only Leeds and Online rows, and every email masked. You wrote no WHERE clause; the platform applied it.
A8.run("ALTER TABLE {bookings_governed} ALTER COLUMN customer_email SET MASK {mask_email}")
A8.run("ALTER TABLE {bookings_governed} SET ROW FILTER {city_filter} ON (city)")
display(A8.sql("SELECT booking_id, city, customer_email FROM {bookings_governed} LIMIT 10"))

# COMMAND ----------
# WHAT: tests the policies independently, and confirms the source table was not changed.
# LOOK FOR: "Policy enforcement observed; source data unchanged."
governed = A8.sql("SELECT DISTINCT city FROM {bookings_governed}").collect()
assert {r[0] for r in governed} == {"Leeds", "Online"}  # the filter hides every other city
assert A8.sql("SELECT count(*) FROM {bookings_governed} WHERE customer_email NOT LIKE '%***%'").first()[0] == 0
assert A8.sql("SELECT count(*) FROM {bookings} WHERE customer_email LIKE '%***%'").first()[0] == 0  # source untouched
assert A8.sql("SELECT count(*) FROM {bookings_governed}").first()[0] < spark.table(A8.t("bookings")).count()
print("Policy enforcement observed; source data unchanged.")
A8.links(("Governed copy: inspect mask and row filter", "table", "bookings_governed"),
         ("SQL mask definition", "function", "mask_email"))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** on the governed copy, find the mask indicator beside `customer_email` and the row filter on
# MAGIC **Overview**. Open the `mask_email` function. Query the table in the SQL editor by its full name: the policy still applies.
# MAGIC
# MAGIC **UI alternative to ALTER TABLE:** after creating the functions, Table → Row filter → Add → `city_filter` on `city`;
# MAGIC then the email column → Mask → `mask_email`.
# MAGIC
# MAGIC **Think critically**
# MAGIC - The table still shows `customer_name`. Masking part of an email does not make a person anonymous.
# MAGIC - You own the unfiltered source, so you can still read everything there. A real analyst must not have
# MAGIC   access to the source as well as the governed copy.
# MAGIC - This proves the policy runs on this copy. It does not protect data from its owner.
# MAGIC
# MAGIC ### Exercises
# MAGIC 2.1 counts governed rows per city; 2.2 checks that no unmasked email is visible. Put SQL between the quotes.

# COMMAND ----------
# WHAT: checks your answer to 2.1.
answer_2_1 = """"""
A8.check("2.1", answer_2_1)

# COMMAND ----------
# WHAT: checks your answer to 2.2.
answer_2_2 = """"""
A8.check("2.2", answer_2_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Trace and audit (10 minutes)
# MAGIC - **Lineage** answers "where did this data come from?"
# MAGIC - **Audit** answers "who did what, and when?"
# MAGIC
# MAGIC Neither proves the data is correct. In the governed copy's **Lineage** tab, expand Bookings and Events.
# MAGIC Databricks records lineage from queries it runs, not from processing done elsewhere, such as on a laptop.
# MAGIC
# MAGIC Lineage and audit are also stored in **system tables**. These may be restricted or unavailable, especially
# MAGIC in Free Edition, and can take hours to update. The optional cell reads only recent rows for your identity.
# MAGIC A permission error is a limitation to note, not a reason to ask for broad admin access.

# COMMAND ----------
# WHAT: if switched on, queries the lineage and audit system tables for your governed copy.
# LOOK FOR: rows, an empty result (data not arrived yet), or an "unavailable" message. All three are acceptable.
if A8.gate("read_system_evidence", "Try restricted lineage/audit system tables?"):
    from a8learn import sql_string  # safely quotes text values inside SQL
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
# MAGIC **Recap: explain before moving on**
# MAGIC - Why is a tag not a permission?
# MAGIC - Why does the policy affect you, the owner?
# MAGIC - What would you need to show that two different users see different rows?
# MAGIC - Which grants on the source would you remove for an analyst?
# MAGIC
# MAGIC The policies stay attached for your next visit. Cleanup drops the copy before its functions, so nothing is left
# MAGIC pointing at a missing function.

# COMMAND ----------
# WHAT: summarises the module and names the next notebook.
A8.next_step(["A documented/tagged policy sandbox", "Two UC SQL functions",
              "Observed email masking and city filtering", "A distinction between lineage, audit and access grants"],
             "03_predictive_ml", "Predict turnout, track and register a model")
