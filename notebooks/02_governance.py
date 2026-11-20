# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 2. Control who can see what
# MAGIC **Where this sits:** governance across every analytics level, not a separate analytics level.
# MAGIC
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
# MAGIC | **Policy:** which rows and values do I see? | Row filters, column masks | Only Leeds rows; emails hidden |
# MAGIC
# MAGIC Privileges are inherited downwards: to read a table you need `USE CATALOG` on its catalog, `USE SCHEMA` on its
# MAGIC schema and `SELECT` on the table. A filter written in a notebook can be deleted by whoever runs it;
# MAGIC a Unity Catalog policy is enforced by the platform on every query, from any tool.

# COMMAND ----------
# MAGIC %run ./_config

# COMMAND ----------

# WHAT: checks the Module 1 prerequisites.
# LOOK FOR: no error if your source events and bookings tables exist.
A8.require("events", "bookings")

# COMMAND ----------
# WHAT: resolves your validated object names for the SQL examples.
# LOOK FOR: no output; later sections reuse these real names.
events = A8.t("events")
bookings = A8.t("bookings")
bookings_governed = A8.t("bookings_governed")
mask_email = A8.t("mask_email")
city_filter = A8.t("city_filter")

# COMMAND ----------
# WHAT: opens the permissions pages.
# LOOK FOR: links to your schema and source bookings table.
A8.links(("Schema permissions", "schema", ""), ("Source bookings", "table", "bookings"))

# COMMAND ----------
# WHAT: shows privileges on your bookings table.
# LOOK FOR: grants, possibly empty if you hold privileges only as owner.
display(spark.sql(f"SHOW GRANTS ON TABLE {bookings}"))

# COMMAND ----------
# WHAT: shows the identity used to evaluate policies.
# LOOK FOR: your current Databricks user.
display(spark.sql("SELECT current_user() AS querying_identity"))

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

# WHAT: creates a policy sandbox without replacing an existing owned copy.
# LOOK FOR: a new joined table on first run; existing policies survive reruns.
A8.guard("bookings_governed")
if not A8.exists("bookings_governed"):
    spark.sql(f"""CREATE TABLE {bookings_governed} USING DELTA
COMMENT 'a8-databricks-learning synthetic contacts: demonstration policies only'
AS SELECT b.*, e.city FROM {bookings} b JOIN {events} e USING (event_id)""")

# COMMAND ----------
# WHAT: labels the sandbox with descriptive tags.
# LOOK FOR: the same metadata on every rerun; tags do not restrict access.
A8.guard("bookings_governed")
spark.sql(f"""ALTER TABLE {bookings_governed} SET TAGS ('a8_data_class' = 'synthetic_contact',
'a8_purpose' = 'learning')""")

# COMMAND ----------
# WHAT: shows the sandbox's metadata.
# LOOK FOR: its comment and a Tags section with a8_data_class and a8_purpose.
display(spark.sql(f"DESCRIBE TABLE EXTENDED {bookings_governed}"))

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

# WHAT: defines a demo email mask for every reader.
# LOOK FOR: an owned SQL function returning a masked string or NULL.
A8.guard("mask_email")
spark.sql(f"""CREATE OR REPLACE FUNCTION {mask_email}(email STRING)
RETURNS STRING COMMENT 'a8-databricks-learning demo mask for every reader'
RETURN CASE WHEN email IS NULL THEN NULL
ELSE concat(left(email, 1), '***@example.com') END""")

# COMMAND ----------
# WHAT: defines the demonstration city allow-list.
# LOOK FOR: an owned SQL function that allows Leeds and Online only.
A8.guard("city_filter")
spark.sql(f"""CREATE OR REPLACE FUNCTION {city_filter}(city STRING)
RETURNS BOOLEAN COMMENT 'a8-databricks-learning demo cities for every reader'
RETURN city IN ('Leeds', 'Online')""")

# COMMAND ----------
# WHAT: shows each policy function's result before attaching it.
# LOOK FOR: masked = f***@example.com, leeds_allowed = true, london_allowed = false.
display(spark.sql(f"""SELECT {mask_email}('fictional@example.com') AS masked,
{city_filter}('Leeds') AS leeds_allowed, {city_filter}('London') AS london_allowed"""))

# COMMAND ----------

# WHAT: attaches the email mask to the sandbox.
# LOOK FOR: successful ALTER TABLE; the source is not changed.
A8.guard("bookings_governed")
spark.sql(f"ALTER TABLE {bookings_governed} ALTER COLUMN customer_email SET MASK {mask_email}")

# COMMAND ----------
# WHAT: attaches the city row filter to the sandbox.
# LOOK FOR: successful ALTER TABLE; the filter receives the city column.
A8.guard("bookings_governed")
spark.sql(f"ALTER TABLE {bookings_governed} SET ROW FILTER {city_filter} ON (city)")

# COMMAND ----------
# WHAT: shows the platform-enforced policy result.
# LOOK FOR: only Leeds and Online rows with masked emails, despite having no WHERE clause.
display(spark.sql(f"SELECT booking_id, city, customer_email FROM {bookings_governed} LIMIT 10"))

# COMMAND ----------

# WHAT: Check: verifies the visible cities.
# LOOK FOR: exactly Leeds and Online, with every other city hidden.
governed = spark.sql(f"SELECT DISTINCT city FROM {bookings_governed}").collect()
A8.expect({r[0] for r in governed} == {"Leeds", "Online"},
          "The row filter must show exactly Leeds and Online.")

# COMMAND ----------
# WHAT: Check: verifies the email mask.
# LOOK FOR: no unmasked email visible in the governed copy.
unmasked = spark.sql(f"""SELECT count(*) FROM {bookings_governed}
WHERE customer_email NOT LIKE '%***%'""").first()[0]
A8.expect(unmasked == 0, "Every visible governed email must be masked.")

# COMMAND ----------
# WHAT: Check: verifies the source has not inherited the mask.
# LOOK FOR: zero masked emails in the source table.
source_masked = spark.sql(f"SELECT count(*) FROM {bookings} WHERE customer_email LIKE '%***%'").first()[0]
A8.expect(source_masked == 0, "Source booking emails must remain unchanged.")

# COMMAND ----------
# WHAT: Check: verifies the filter reduces the visible row count.
# LOOK FOR: fewer governed rows than source bookings.
A8.expect(spark.table(bookings_governed).count() < spark.table(bookings).count(),
          "The governed copy must expose fewer rows than the source.")
print("Policy enforcement observed; source data unchanged.")

# COMMAND ----------
# WHAT: opens the attached policies and mask definition.
# LOOK FOR: links to the sandbox and its SQL mask function.
A8.links(("Governed copy: inspect mask and row filter", "table", "bookings_governed"),
         ("SQL mask definition", "function", "mask_email"))

# COMMAND ----------
# MAGIC %md
# MAGIC **UI step:** on the governed copy, find the mask indicator beside `customer_email` and the row filter on
# MAGIC **Overview**. Open the `mask_email` function. Query the table in the SQL editor by its full name: the policy
# MAGIC still applies.
# MAGIC
# MAGIC **UI alternative to ALTER TABLE:** after creating the functions, Table → Row filter → Add → `city_filter` on
# MAGIC `city`;
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
# MAGIC Use `IDENTIFIER(a8_bookings_governed)` as the table name, as you would in a `%sql` cell.
# MAGIC Python cells use real names resolved with `A8.t` near the top; values use `spark.sql(..., args={...})`.

# COMMAND ----------

# WHAT: Check: compares your exercise 2.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, or feedback on your query.
answer_2_1 = """"""
A8.check("2.1", answer_2_1)

# COMMAND ----------

# WHAT: Check: compares your exercise 2.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, or feedback on your query.
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
# MAGIC in Free Edition, and can take hours to update. The optional cells read only recent rows for your identity.
# MAGIC A permission error is a limitation to note, not a reason to ask for broad admin access.

# COMMAND ----------

# WHAT: records whether you want to read optional system evidence.
# LOOK FOR: a yes/no widget; the default skips both restricted system-table queries.
read_system_evidence = A8.gate("read_system_evidence", "Try restricted lineage/audit system tables?")
evidence_args = {"user": A8.cfg.user, "table_name": A8.name("bookings_governed"),
                 "table_pattern": f"%{A8.name('bookings_governed')}%"}

# COMMAND ----------
# WHAT: optionally reads recent lineage for your governed copy.
# LOOK FOR: rows, no rows yet, or an unavailable message; none requires broader permissions.
if read_system_evidence:
    try:
        display(spark.sql("""SELECT event_time, source_table_full_name, target_table_full_name
FROM system.access.table_lineage
WHERE event_date >= date_sub(current_date(), 1)
AND created_by = :user AND target_table_name = :table_name
ORDER BY event_time DESC LIMIT 10""", args=evidence_args))
    except Exception as error:
        print(f"lineage unavailable ({type(error).__name__}). "
              "Use Catalog lineage and ask your admin about availability.")
else:
    print("System tables skipped. Inspect Catalog lineage instead.")

# COMMAND ----------
# WHAT: optionally reads recent audit events for your identity and governed copy.
# LOOK FOR: rows, no rows yet, or an unavailable message; audit records can arrive late.
if read_system_evidence:
    try:
        display(spark.sql("""SELECT event_time, service_name, action_name
FROM system.access.audit WHERE event_date >= date_sub(current_date(), 1)
AND user_identity.email = :user
AND to_json(request_params) LIKE :table_pattern
ORDER BY event_time DESC LIMIT 10""", args=evidence_args))
    except Exception as error:
        print(f"audit unavailable ({type(error).__name__}). Use Catalog lineage and ask your admin about availability.")
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
# LOOK FOR: the outcomes you can explain and your next lesson.
A8.next_step(["A documented/tagged policy sandbox", "Two UC SQL functions",
              "Observed email masking and city filtering", "A distinction between lineage, audit and access grants"],
             "05_predictive_ml", "Predict turnout, track and register a model")
