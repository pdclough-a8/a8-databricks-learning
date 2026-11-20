# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1b. Describe the business with AI/BI and Genie
# MAGIC **Where this sits:** descriptive analytics, what happened or is booked. Prediction is Module 3;
# MAGIC diagnostic analytics follows in Module 1c; prescriptive analytics is planned separately.
# MAGIC
# MAGIC **Outcome:** build a private draft dashboard and a Genie space over your own governed event metrics,
# MAGIC then prove their answers with SQL. Descriptive analytics asks **what happened or is booked**, not what will
# MAGIC happen or why. Event management is the case study; Databricks datasets, dashboards and Genie are the skills.
# MAGIC
# MAGIC **60–75 minutes, an estimate:** orient 5 · metrics/view 15 · dashboard 20 · Genie 20 · transfer/recap 10.
# MAGIC **Before you start:** finish `00_setup` and `01_lakehouse_data`. Modules 2 and 3 are not prerequisites.
# MAGIC Use the saved learner tag and schema, normally `workspace.default` on Free Edition.
# MAGIC All data is synthetic, frozen at **20 November 2026**. Do not use today's date or substitute customer data.
# MAGIC
# MAGIC ## 1. Choose the Free Edition route first
# MAGIC - Notebook: select **Serverless**. No package installation or restart is needed.
# MAGIC - Dashboard/Genie: use your **existing serverless SQL warehouse**. Free Edition allows one warehouse,
# MAGIC   limited to 2X-Small, under fair-use quotas. Do not create or resize a warehouse or start a paid trial.
# MAGIC - You need Databricks SQL access, CAN USE on the warehouse, and USE CATALOG / USE SCHEMA / SELECT on your
# MAGIC   lesson sources, plus CREATE TABLE on your existing schema to create a view. Do not grant yourself privileges.
# MAGIC - If a feature, permission or quota is unavailable, **stop that branch** and record it as blocked.
# MAGIC   The SQL-only fallback below still teaches metrics; it does not count as completing dashboard or Genie.
# MAGIC
# MAGIC **Approval and cost boundary:** this notebook can create or replace exactly one tagged view, behind a
# MAGIC default-no switch, plus an optional dashboard file behind a second default-no switch.
# MAGIC Reads consume compute quota. The later UI steps save a dashboard and Genie configuration;
# MAGIC asking Genie invokes partner-powered AI and can run SQL. On paid workspaces these operations may incur charges.
# MAGIC Obtain your workspace owner's approval before those actions. The SDK reads the generated file's object type;
# MAGIC it does not create dashboards or Genie spaces through an API. No model endpoint, job or schedule is deployed.
# MAGIC An assisting agent must ask separately before performing any live cloud work.
# MAGIC Keep assets in your own user folder, inspect inherited access, and stop if it is not private enough.
# MAGIC Do not publish, share, embed credentials for dashboard viewers, or alter permissions in this lesson.
# MAGIC
# MAGIC **Names:** current documentation calls Genie Spaces **Genie Agents**. Your sidebar might still say
# MAGIC **Genie** or **Genie Spaces**. Use its natural-language data chat, not Genie Code (the coding assistant).
# MAGIC We use Chat mode, not multi-step Agent mode. Availability and labels vary; the UI route is not live validated.

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; JSON reads the dashboard template and the SDK checks how the file was stored.
import json

from databricks.sdk import WorkspaceClient

# COMMAND ----------

# WHAT: checks the three source objects created in Module 1 are present.
# LOOK FOR: no output; a missing source names the prerequisite notebook.
A8.require("events", "bookings", "feedback")

# COMMAND ----------
# WHAT: resolves your validated SQL names for this lesson.
# LOOK FOR: no output; SQL copied into another editor will use these real names.
events = A8.t("events")
bookings = A8.t("bookings")
feedback = A8.t("feedback")
event_metrics = A8.t("event_metrics")

# COMMAND ----------
# WHAT: opens the schema and SQL editor without creating anything.
# LOOK FOR: links to your saved namespace and the workspace SQL editor.
A8.links(("Your schema", "schema", ""), ("SQL editor", "sql_editor", ""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Define a metric before drawing a chart
# MAGIC **Grain** means what one row represents. Our reporting view has **one row per event**, including events
# MAGIC with no bookings or feedback. A direct events → bookings → feedback join repeats booking rows and inflates
# MAGIC tickets. Aggregate each child table by event first, then LEFT JOIN the two summaries onto events.
# MAGIC
# MAGIC | Field | Meaning and aggregation rule |
# MAGIC |---|---|
# MAGIC | `event_status` | completed or scheduled; this is the event's status, not a booking status |
# MAGIC | `confirmed_bookings` | count of confirmed booking rows; not people or tickets |
# MAGIC | `confirmed_tickets` | sum of tickets on confirmed bookings only, including free tickets |
# MAGIC | `capacity`, `available_seats` | event capacity; capacity minus confirmed tickets |
# MAGIC | `fill_rate` | confirmed tickets / capacity, a fraction; do not add or average it across events |
# MAGIC | `known_outcome_tickets` | confirmed tickets with a known attendance flag, completed events only |
# MAGIC | `attended_tickets` | tickets on those bookings whose attendance flag is true; NULL without known outcomes |
# MAGIC | `attendance_rate` | attended tickets / known-outcome tickets, not / all future bookings |
# MAGIC | `feedback_count`, `rating_sum` | count and sum of feedback ratings; additive across events |
# MAGIC | `average_rating` | rating_sum / feedback_count; NULL when no responses, never zero by default |
# MAGIC
# MAGIC A booking's single attendance flag stands for its whole party here. This is a **ticket-weighted proxy**,
# MAGIC not measured individual attendance. Feedback is self-selected, not representative of every attendee.
# MAGIC There is no payment ledger: list price times tickets is **not recognised revenue**, so we do not report revenue.
# MAGIC These projections omit names, emails and free text, but are **not a security policy or anonymisation**.
# MAGIC Module 2 teaches enforcement. A chart filter or Genie instruction does not restrict a user's other access.
# MAGIC
# MAGIC **Predict:** what should an empty event show? Zero confirmed tickets, its full capacity available,
# MAGIC no average rating, and no attendance rate. Why would `WHERE b.status = 'confirmed'` after a LEFT JOIN lose it?
# MAGIC
# MAGIC The next cell only prepares native SQL; it does not run it. The single CTE query is kept together so you can
# MAGIC read the pre-aggregation and joins as one statement. It uses real names because saved views cannot reference
# MAGIC this notebook's SQL session variables.

# COMMAND ----------

# WHAT: prepares the one-row-per-event reporting query without executing it.
# LOOK FOR: no output; bookings and feedback are aggregated separately before their joins.
metrics_sql = f"""WITH booking_totals AS (
  SELECT event_id, count(*) AS confirmed_bookings, sum(tickets) AS confirmed_tickets,
    sum(CASE WHEN attended IS NOT NULL THEN tickets ELSE 0 END) AS known_outcome_tickets,
    sum(CASE WHEN attended = true THEN tickets ELSE 0 END) AS attended_tickets
  FROM {bookings} WHERE status = 'confirmed' GROUP BY event_id
), feedback_totals AS (
  SELECT event_id, count(*) AS feedback_count, sum(rating) AS rating_sum
  FROM {feedback} GROUP BY event_id
)
SELECT e.event_id, e.event_name, e.topic, e.format, e.city, e.event_date, e.status AS event_status,
  e.capacity, coalesce(b.confirmed_bookings, 0) AS confirmed_bookings,
  coalesce(b.confirmed_tickets, 0) AS confirmed_tickets,
  e.capacity - coalesce(b.confirmed_tickets, 0) AS available_seats,
  1.0 * coalesce(b.confirmed_tickets, 0) / nullif(e.capacity, 0) AS fill_rate,
  CASE WHEN e.status = 'completed' THEN coalesce(b.known_outcome_tickets, 0)
    ELSE 0 END AS known_outcome_tickets,
  CASE WHEN e.status = 'completed' AND b.known_outcome_tickets > 0
    THEN b.attended_tickets END AS attended_tickets,
  CASE WHEN e.status = 'completed'
    THEN 1.0 * b.attended_tickets / nullif(b.known_outcome_tickets, 0) END AS attendance_rate,
  coalesce(f.feedback_count, 0) AS feedback_count, coalesce(f.rating_sum, 0) AS rating_sum,
  1.0 * f.rating_sum / nullif(f.feedback_count, 0) AS average_rating
FROM {events} e
LEFT JOIN booking_totals b ON e.event_id = b.event_id
LEFT JOIN feedback_totals f ON e.event_id = f.event_id"""

# COMMAND ----------
# WHAT: shows the exact SQL and view name for inspection before the write.
# LOOK FOR: only your tagged sources and your tagged event_metrics view.
print("Write target:", event_metrics)
print(metrics_sql)

# COMMAND ----------
# MAGIC %md
# MAGIC ### Create deliberately
# MAGIC This writes only the view definition, not a copy of the source data. After reviewing the target above,
# MAGIC run the next cell: it adds a `create_reporting_view` widget above the notebook, defaulting to **no**.
# MAGIC Set it to **yes**, then run the create cell. With no, the create cell skips the write and the following
# MAGIC check stops with a clear message, so Run All cannot create the view by accident.
# MAGIC Rerunning yes replaces the same owned, course-marked view; it never appends rows. An ownership or marker
# MAGIC collision stops the write. Do not adopt or rename somebody else's object.
# MAGIC
# MAGIC On resume, review and rerun these cells before continuing. The widget may retain your previous choice,
# MAGIC so return it to no when you finish. No source table is changed.

# COMMAND ----------

# WHAT: asks for permission to create or replace your reporting view.
# LOOK FOR: a create_reporting_view widget above the notebook, defaulting to no.
create_reporting_view = A8.gate("create_reporting_view", "Approve creating/replacing your reporting view?")
print("Approved:" if create_reporting_view else "Not approved yet. Set the widget to yes, then rerun this cell.",
      event_metrics)

# COMMAND ----------
# WHAT: creates the reporting view only after your opt-in and an ownership check.
# LOOK FOR: successful CREATE VIEW, or "View not created" if the widget is no.
if create_reporting_view:
    A8.guard("event_metrics")
    spark.sql(f"""CREATE OR REPLACE VIEW {event_metrics}
COMMENT 'a8-databricks-learning one row per event; synthetic snapshot 2026-11-20; no personal fields'
AS {metrics_sql}""")
else:
    print("View not created. Set create_reporting_view to yes and rerun the two cells above.")

# COMMAND ----------
# WHAT: Check: stops here if the reporting view does not exist yet.
# LOOK FOR: no output when the view exists; otherwise a card naming the missing view.
A8.require("event_metrics")

# COMMAND ----------
# WHAT: previews the reporting view without exposing booking-level personal fields.
# LOOK FOR: event metrics, including NULL ratings/attendance where evidence is absent.
display(spark.sql(f"SELECT * FROM {event_metrics} ORDER BY event_id LIMIT 10"))

# COMMAND ----------
# WHAT: Check: verifies the reporting grain matches the source grain.
# LOOK FOR: one metrics row per event; baseline fixtures contain 60.
source_count = spark.table(events).count()
metric_counts = spark.sql(f"""SELECT count(*) AS rows, count(DISTINCT event_id) AS ids
FROM {event_metrics}""").first()
A8.expect(metric_counts["rows"] == metric_counts["ids"] == source_count,
          "The reporting view must contain exactly one row for every source event.")

# COMMAND ----------
# WHAT: Check: reconciles ticket and feedback totals directly to the separate sources.
# LOOK FOR: pass messages; joining feedback must not multiply confirmed tickets.
reported = spark.sql(f"""SELECT sum(confirmed_tickets) AS tickets, sum(feedback_count) AS responses
FROM {event_metrics}""").first()
source_tickets = spark.sql(f"SELECT coalesce(sum(tickets), 0) FROM {bookings} WHERE status = 'confirmed'").first()[0]
A8.expect(reported["tickets"] == source_tickets,
          "Confirmed tickets must reconcile to bookings, excluding cancellations.")
A8.expect(reported["responses"] == spark.table(feedback).count(), "Feedback counts must reconcile to feedback rows.")

# COMMAND ----------
# WHAT: Check: confirms future attendance is unknown and no-response ratings remain NULL.
# LOOK FOR: zero impossible rows; NULL must not silently become a no-show or zero-star rating.
invalid = spark.sql(f"""SELECT count(*) FROM {event_metrics}
WHERE (event_status = 'scheduled' AND (attended_tickets IS NOT NULL OR attendance_rate IS NOT NULL))
OR (feedback_count = 0 AND average_rating IS NOT NULL)""").first()[0]
A8.expect(invalid == 0, "Scheduled attendance and ratings without feedback must remain unknown.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Build a small AI/BI dashboard by hand (about 5 minutes)
# MAGIC A dashboard **dataset** is the SQL result available to widgets, not a new Delta table.
# MAGIC A widget aggregates that dataset at its chart grain. We retain event rows so field filters can change
# MAGIC the set of events **before each widget aggregates**. A single grand-total dataset would not retain city/date.
# MAGIC A persisted view reads current tables; a dashboard may serve cached results until refreshed.
# MAGIC
# MAGIC **Pause for UI-write approval.** Creating a dashboard saves a workspace object; running its dataset uses
# MAGIC your SQL warehouse. If you are working with a tutor/agent, approve this exact scope before it acts.
# MAGIC Do these steps yourself only when ready:
# MAGIC 1. **New → Dashboard** (AI/BI, not legacy). Keep it in your own user folder. Inspect **Share** access without
# MAGIC    adding anyone; enclosing-folder permissions may be inherited. If unsuitable, stop and ask the owner.
# MAGIC 2. Use the suggested title printed below. Keep the dashboard a **draft**; do not click Publish.
# MAGIC 3. Select the existing serverless warehouse, then **Data → Add SQL dataset**. Name it `Event metrics`.
# MAGIC    Paste the SQL printed below, run it and inspect the result. Expect 60 rows with baseline fixtures.
# MAGIC 4. On the page/canvas add **one counter**: Events, COUNT(event_id). Then **Add a filter (field/parameter)**:
# MAGIC    single value on `city`. Select Leeds and watch the counter change; reset it to All.
# MAGIC    That is the core idea: widgets aggregate one dataset, and field filters narrow it first.
# MAGIC 5. Stop building by hand here. Section 3b loads the complete dashboard from a file, so you can compare
# MAGIC    your draft with a finished one. Delete your hand-built draft afterwards if you do not need it.

# COMMAND ----------

# WHAT: prepares the dashboard dataset using real names, not notebook session variables.
# LOOK FOR: no output; dimensions and additive fields remain at event grain for filtering.
dashboard_sql = f"""SELECT event_id, event_name, topic, format, city, event_date, event_status,
capacity, confirmed_bookings, confirmed_tickets, available_seats, fill_rate,
known_outcome_tickets, attended_tickets, attendance_rate, feedback_count, rating_sum, average_rating
FROM {event_metrics}"""

# COMMAND ----------
# WHAT: prints the private draft title and dataset SQL to copy into the dashboard Data tab.
# LOOK FOR: your tag in the title and a fully qualified view name.
print(f"Dashboard title: A8 | {A8.cfg.tag} | Event snapshot")
print(dashboard_sql)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3b. A dashboard is a file: load the complete version
# MAGIC An AI/BI dashboard draft is stored as a `.lvdash.json` file: a list of **datasets** (SQL) and **pages** of
# MAGIC **widgets**, each with its query fields and a chart spec. Open `dashboards/event_snapshot.lvdash.template.json`
# MAGIC in this Git folder to read one. It deliberately has no SQL and is not named `.lvdash.json`, so it is not itself
# MAGIC a dashboard. The next cells copy it, insert `dashboard_sql` with **your** view name, and save it to your own
# MAGIC `a8learn` user folder. Exporting, editing and importing this file is how dashboards move between workspaces;
# MAGIC deploying them automatically is Module 8.
# MAGIC
# MAGIC Writing the file is a workspace write, so it is opt-in: run the next cell, set `write_dashboard_file` to
# MAGIC **yes**, rerun that gate cell, then run the following cells. An existing file is left unchanged; to
# MAGIC regenerate, move your own copy to trash first. Opening the dashboard runs its dataset on your SQL warehouse.

# COMMAND ----------

# WHAT: asks for permission to write your dashboard file.
# LOOK FOR: a write_dashboard_file widget above the notebook, defaulting to no, and the exact target path.
write_dashboard_file = A8.gate("write_dashboard_file", "Write your dashboard file to your user folder?")
dashboard_path = A8.dashboard_path
print("Approved:" if write_dashboard_file else "Not approved yet. Set the widget to yes, then rerun this cell.",
      dashboard_path)

# COMMAND ----------
# WHAT: fills the supplied template with your dataset SQL; nothing is written yet.
# LOOK FOR: no output; dashboard is an ordinary Python dict parsed from JSON.
template = ROOT / "dashboards" / "event_snapshot.lvdash.template.json"
dashboard = json.loads(template.read_text(encoding="utf-8"))
dashboard["datasets"][0]["queryLines"] = dashboard_sql.splitlines(keepends=True)

# COMMAND ----------
# WHAT: Check: confirms the file reads only your view and every widget uses that one dataset.
# LOOK FOR: two pass messages before anything is written.
A8.expect(len(dashboard["datasets"]) == 1 and event_metrics in "".join(dashboard["datasets"][0]["queryLines"]),
          "The dashboard must have one dataset reading your event_metrics view.")
used = {q["query"]["datasetName"] for item in dashboard["pages"][0]["layout"]
        for q in item["widget"].get("queries", [])}
A8.expect(used == {dashboard["datasets"][0]["name"]}, "Every widget must use the Event metrics dataset.")

# COMMAND ----------
# WHAT: writes the dashboard file once, after your opt-in; never overwrites an existing file.
# LOOK FOR: "Written", "Already exists" or "Not written".
if not write_dashboard_file:
    print("Not written. Set write_dashboard_file to yes and rerun the cells above.")
elif dashboard_path.exists():
    print("Already exists, left unchanged:", dashboard_path)
else:
    dashboard_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    print("Written:", dashboard_path)

# COMMAND ----------
# WHAT: reads how the workspace stored the file; this is a read, not a write.
# LOOK FOR: DASHBOARD means open it directly; FILE means use the import route below.
if dashboard_path.exists():
    status = WorkspaceClient().workspace.get_status(str(dashboard_path).removeprefix("/Workspace"))
    print("Stored as:", status.object_type)

# COMMAND ----------
# MAGIC %md
# MAGIC ### Open the dashboard
# MAGIC Go to **Workspace → Users → you → a8learn**. If the cell above printed **DASHBOARD**, open
# MAGIC *A8 &lt;tag&gt; event snapshot*. If it printed **FILE**, download that file from its menu, then use
# MAGIC **Dashboards → Import dashboard from file**. Then move the generated file in `a8learn` to trash.
# MAGIC Either way: select your existing serverless warehouse if asked, keep it a **draft**, do not publish or share.
# MAGIC Behaviour of a file written from a notebook is not live validated yet; record which route you used.
# MAGIC
# MAGIC ### What the complete dashboard contains, one dataset, one page
# MAGIC Compare each widget below with the JSON and with your own draft. The heading text box says:
# MAGIC "Confirmed tickets are not attendees. Ratings represent respondents only. Filters are not security."
# MAGIC Keep labels readable, use GBP only for actual GBP measures (none here), and never rely on colour alone.
# MAGIC A8 text branding is sufficient; palette values are provisional.
# MAGIC
# MAGIC | Widget / title | Configuration |
# MAGIC |---|---|
# MAGIC | Counter: Events | COUNT(event_id), zero decimals; count events, not confirmed_bookings |
# MAGIC | Counter: Confirmed tickets | SUM(confirmed_tickets), zero decimals |
# MAGIC | Bar: Confirmed tickets by city | X city, Y SUM(confirmed_tickets), sort descending |
# MAGIC | Bar: Confirmed tickets by event date | X event_date, calendar MONTH, Y SUM(confirmed_tickets) |
# MAGIC | Table: Event detail | event_id, event_name, city, event_date, event_status, capacity, confirmed_tickets, |
# MAGIC | continued | available_seats, fill_rate, feedback_count, average_rating; one row per event |
# MAGIC
# MAGIC Format the table's `fill_rate` as **percentage** (0.5 means 50%, do not multiply twice).
# MAGIC Format `average_rating` to two decimals and leave missing values blank/NULL. Sort the table by event_date.
# MAGIC This table keeps ratios at event grain; **do not add an AVG(average_rating) or AVG(fill_rate) counter**.
# MAGIC For grouped ratings use SUM(rating_sum) / SUM(feedback_count); for grouped fill use
# MAGIC SUM(confirmed_tickets) / SUM(capacity). A small event and a large event must not receive equal weight.
# MAGIC
# MAGIC ### Prove that the filters work
# MAGIC The file includes three **field filters**, not SQL parameters. Inspect each one's field binding:
# MAGIC - **City:** single value on `Event metrics.city`, default All.
# MAGIC - **Event status:** single value on `Event metrics.event_status`, default All.
# MAGIC - **Event date:** date range on `Event metrics.event_date`, default full range/All.
# MAGIC Each is bound to that dataset, so it affects **every** widget. Check no widget is set to ignore filters.
# MAGIC Do not select "last 30 days": this is a fixed historical snapshot and includes scheduled future events.
# MAGIC
# MAGIC 1. Clear every filter and cross-filter. Compare both counters with the `all_events` SQL below.
# MAGIC 2. Select status **scheduled**. Expect **12 events** on unmodified fixtures. Compare tickets with
# MAGIC    `scheduled_events`. All five widgets must update, not only the table.
# MAGIC 3. Also select city **Leeds**. Compare counters and table rows with `scheduled_leeds`.
# MAGIC 4. Also set event date **1 December 2026 through 31 December 2026**, inclusive.
# MAGIC    Compare with `scheduled_leeds_december`. This tests the date filter together with city and status.
# MAGIC 5. Reset **all three** filters and any chart selection. Prove the original counts return.
# MAGIC    If a result differs, inspect the dataset, aggregation and filter bindings before changing SQL.
# MAGIC
# MAGIC **Field filters control presentation, not permissions.** Small datasets may be filtered in the browser.
# MAGIC Draft editing uses your access; publishing with data permissions can expose data under another identity.
# MAGIC Publishing, sharing, refresh schedules and delivery subscriptions are deferred, not required to finish.

# COMMAND ----------

# WHAT: prepares SQL reference queries for the dashboard's successive filter states.
# LOOK FOR: no output; predicates match exactly the UI selections described above.
dashboard_checks = {
    "all_events": "",
    "scheduled_events": "WHERE event_status = 'scheduled'",
    "scheduled_leeds": "WHERE event_status = 'scheduled' AND city = 'Leeds'",
    "scheduled_leeds_december": """WHERE event_status = 'scheduled' AND city = 'Leeds'
AND event_date >= '2026-12-01' AND event_date <= '2026-12-31'""",
}
dashboard_checks = {
    name: f"""SELECT count(*) AS events, sum(confirmed_tickets) AS confirmed_tickets
FROM {event_metrics} {predicate}"""
    for name, predicate in dashboard_checks.items()
}

# COMMAND ----------
# WHAT: runs the reference SQL for each dashboard filter state.
# LOOK FOR: query text and counters to compare with the draft, not a claim that the UI passed.
for name, query in dashboard_checks.items():
    print(name, "\n", query)
    display(spark.sql(query))

# COMMAND ----------
# MAGIC %md
# MAGIC ### Checkpoint D, record observed evidence
# MAGIC In your own notes record the draft URL/ID, dataset/view name, warehouse label, unfiltered counters,
# MAGIC scheduled counters, scheduled Leeds counters, December counters and the restored unfiltered result.
# MAGIC Explain why SUM(tickets) differs from COUNT(bookings), and why the two child tables were aggregated first.
# MAGIC A successful notebook cell does **not** certify a rendered dashboard. Mark D blocked if you used SQL only.
# MAGIC
# MAGIC ## 4. Give Genie a small, well-defined analytical scope
# MAGIC Genie uses an LLM to translate a question into SQL over configured Unity Catalog data and explain results.
# MAGIC It is not the deterministic dashboard, not a trained attendance model, and not a document-RAG implementation.
# MAGIC Instructions help but do not guarantee correct SQL, enforce permissions, or retrain the model.
# MAGIC
# MAGIC **Pause for UI/AI approval.** Creating/configuring the space saves metadata. New UIs may automatically open
# MAGIC Genie Code and propose context when you create it; this can invoke AI and inspect attached data.
# MAGIC Questions, benchmarks, regenerations and refreshes consume quota/compute; on paid workspaces costs may apply.
# MAGIC Use only this synthetic aggregate view. No credentials, real personal data or third-party connections.
# MAGIC
# MAGIC 1. Open **Genie Agents / Genie / Genie Spaces → New**. Attach **only** the exact `event_metrics` view printed
# MAGIC    below. Do not attach raw bookings, feedback, volumes, functions, MCP tools or the predictive forecast view.
# MAGIC 2. Review the selected data before Create. Decline automatic context suggestions you have not checked.
# MAGIC    If the view is not selectable, stop and record the feature/permission issue; do not broaden the sources.
# MAGIC 3. Under **Configure → Settings**, use the suggested title and your existing serverless warehouse.
# MAGIC    Keep the object in your own user folder. Inspect inherited access; do not share or change ACLs.
# MAGIC    Selecting a warehouse stores the author's compute access for Genie; UC data access is still checked per user.
# MAGIC    Do not mistake this for permission to publish a dashboard with embedded data permissions.
# MAGIC 4. Under **Configure → Sources/Data**, describe this source as "one row per event, bookings and feedback
# MAGIC    pre-aggregated separately; synthetic snapshot 2026-11-20". Add the metric meanings from section 2 as local
# MAGIC    column descriptions, especially statuses, attendance proxy, rating_sum and the missing-value rules.
# MAGIC    These edits belong to this space, not shared UC source metadata. Do not edit other learners' objects.
# MAGIC 5. Paste the printed **General instructions** into the space's instructions area (often Configure → Text).
# MAGIC    In **Configure → Examples / SQL Queries**, add E1–E3 below as example question/SQL pairs.
# MAGIC    Run their SQL in the SQL editor first, then inspect their results before saving as examples.
# MAGIC    If the current UI uses older labels, match the concept; do not guess missing capabilities.

# COMMAND ----------

# WHAT: prints the exact source, title and paste-ready General instructions for your Genie space.
# LOOK FOR: only your event_metrics view; instructions scope interpretation, not authorisation.
genie_instructions = f"""Use only {event_metrics}; one row per event, synthetic snapshot 20 November 2026.
Answer descriptive questions only. event_status describes events, not bookings.
Confirmed tickets exclude cancelled bookings and include free tickets; bookings are not tickets or people.
For scheduled events attendance is unknown, not zero. For completed attendance use
SUM(attended_tickets) / NULLIF(SUM(known_outcome_tickets), 0). This is a ticket-weighted booking-party proxy.
For grouped fill use SUM(confirmed_tickets) / NULLIF(SUM(capacity), 0); rates are fractions.
For grouped rating use SUM(rating_sum) / NULLIF(SUM(feedback_count), 0); show response counts.
Never average event-level ratios across events. Missing feedback is unknown, not zero.
Use explicit event dates, not current_date(). Clarify ambiguous time/status or what 'best' means.
Do not infer causes, forecast attendance, invent revenue, or supply contact details.
Say the data is insufficient for those questions. Explain filters, units, SQL and limitations."""
print(f"Genie title: A8 | {A8.cfg.tag} | Event questions\nSource: {event_metrics}")
print(genie_instructions)

# COMMAND ----------
# WHAT: prepares three example question/SQL pairs with real, warehouse-ready names.
# LOOK FOR: no output; these examples teach statuses, ticket sums and a weighted rating.
genie_examples = {
    "E1: How many events are completed and how many are scheduled?": f"""SELECT event_status, count(*) AS events
FROM {event_metrics} GROUP BY event_status ORDER BY event_status""",
    "E2: How many confirmed tickets do scheduled events have in each city?": f"""SELECT city,
sum(confirmed_tickets) AS confirmed_tickets FROM {event_metrics}
WHERE event_status = 'scheduled' GROUP BY city ORDER BY city""",
    "E3: What is the average feedback rating by topic for completed events, with response counts?": f"""SELECT topic,
sum(feedback_count) AS feedback_count,
round(1.0 * sum(rating_sum) / nullif(sum(feedback_count), 0), 2) AS average_rating
FROM {event_metrics} WHERE event_status = 'completed' GROUP BY topic ORDER BY topic""",
}

# COMMAND ----------
# WHAT: shows each example's exact SQL and result so you can review it before adding it to Genie.
# LOOK FOR: descriptive results, not AI responses; no Genie request is made by this cell.
for question, query in genie_examples.items():
    print(question, "\n", query)
    display(spark.sql(query))

# COMMAND ----------
# MAGIC %md
# MAGIC ### Ask, inspect, reconcile
# MAGIC With approval, ask E2 once in a **new chat**. Open **Show code / Show generated code**.
# MAGIC Before copying or running generated SQL, inspect that it is a read-only SELECT/WITH over your exact view,
# MAGIC with the scheduled predicate and SUM(confirmed_tickets). Do not run DDL/DML or unknown-source SQL.
# MAGIC Compare its rows with the supplied E2 SQL, not only the prose or chart. Check units, exclusions and ordering.
# MAGIC An example query is curated guidance; do not promise a **Verified** badge. Current trusted-asset behaviour
# MAGIC depends on exact parameterised queries or functions. Even a badge would not prove the business definition.
# MAGIC
# MAGIC ## 5. Test transfer, not just memorised examples
# MAGIC B1–B3 below are **held-out** questions. Do not paste them into General instructions, common questions or
# MAGIC example SQL. If Benchmarks is available, add each question and its supplied **SQL Answer** there, select
# MAGIC **Chat** mode and run this small set once with approval. Do not use Generate SQL to define the right answer.
# MAGIC Otherwise ask them once each in fresh chats and compare manually. Label the method in your notes.
# MAGIC Benchmark runs start fresh conversations; they are not a test of follow-up context.
# MAGIC
# MAGIC Inspect every generated SELECT and compare **all rows/columns**, not just the first number. Ordering alone
# MAGIC is not an error here; numeric rounding must match the supplied two-decimal answers. Review SQL semantics too:
# MAGIC two wrong queries can happen to agree on this small snapshot. A platform "Good" rating is not proof of safety.
# MAGIC If anything fails, keep the evidence and stop. Correct the context and get approval before another live run.

# COMMAND ----------

# WHAT: prepares held-out SQL answers for three new descriptive questions.
# LOOK FOR: no output; these are evaluation references, not additional Genie training examples.
genie_benchmarks = {
    "B1: For scheduled Leeds events, list event_id and available_seats in event_id order.": f"""SELECT event_id,
available_seats FROM {event_metrics}
WHERE event_status = 'scheduled' AND city = 'Leeds' ORDER BY event_id""",
    "B2: For completed events, what is the ticket-weighted attendance percentage by format?": f"""SELECT format,
round(100.0 * sum(attended_tickets) / nullif(sum(known_outcome_tickets), 0), 2) AS attendance_pct
FROM {event_metrics} WHERE event_status = 'completed' GROUP BY format ORDER BY format""",
    "B3: For scheduled events, what is the capacity-weighted fill percentage by topic?": f"""SELECT topic,
round(100.0 * sum(confirmed_tickets) / nullif(sum(capacity), 0), 2) AS fill_pct
FROM {event_metrics} WHERE event_status = 'scheduled' GROUP BY topic ORDER BY topic""",
}

# COMMAND ----------
# WHAT: runs the held-out reference SQL without calling an AI model or Genie.
# LOOK FOR: baseline results you will compare against generated answers, not a Genie quality score.
for question, query in genie_benchmarks.items():
    print(question, "\n", query)
    display(spark.sql(query))

# COMMAND ----------
# MAGIC %md
# MAGIC ### Checkpoint G, include a boundary question
# MAGIC With approval, ask once: **"Why are people not attending, and how much revenue will next month's events earn?"**
# MAGIC Correct handling explains that this snapshot cannot establish causes, forecast attendance or compute revenue.
# MAGIC It may offer descriptive summaries with that limitation. Reject invented causes, forecasts or payment totals.
# MAGIC This needs human review, not SQL scoring. Instructions do not guarantee a refusal.
# MAGIC
# MAGIC Record space URL/ID, attached source, test method, E2 comparison, B1/B2/B3 result comparisons and the boundary
# MAGIC outcome. For each record pass/fail/blocked plus the checked SQL or a short redacted difference and your
# MAGIC explanation. Do not store raw conversations, credentials or personal workspace paths in this repository.
# MAGIC Passing three small tests is evidence for those questions only, not a production accuracy or security claim.
# MAGIC
# MAGIC ## 6. Your turn, change, fill a gap, transfer
# MAGIC - **Change:** select a different city in the dashboard. Predict the counter change and verify it with SQL.
# MAGIC - **Gap 1b.1:** fill in scheduled confirmed tickets by city. Hint: SUM, not COUNT.
# MAGIC - **Gap 1b.2:** compute completed-event ratings by topic, weighted by feedback counts.
# MAGIC - **Transfer:** choose a new descriptive question (for example, available seats by format for scheduled
# MAGIC   events), state its grain/status/units, write and run your own reference SELECT, then, only with approval,
# MAGIC   ask Genie and inspect the SQL. Do not promote an unchecked response to an example.
# MAGIC
# MAGIC Exercises use this notebook's `IDENTIFIER(a8_event_metrics)`. Dashboard/Genie/SQL editor sessions do not
# MAGIC inherit that variable; use the real names printed above. Blank answers reveal hints; use
# MAGIC `A8.solution("1b.2")` if stuck. A correct query plus an explanation, not just a green cell, completes the task.

# COMMAND ----------

# WHAT: Check: compares your scheduled-tickets-by-city SQL with the supplied answer.
# LOOK FOR: a hint for a blank answer, otherwise feedback about your result.
answer_1b_1 = """"""
A8.check("1b.1", answer_1b_1)

# COMMAND ----------
# WHAT: Check: compares your feedback-weighted topic ratings with the supplied answer.
# LOOK FOR: a hint or feedback; averaging per-event averages is deliberately incorrect.
answer_1b_2 = """"""
A8.check("1b.2", answer_1b_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Pause, resume and clean up your exact assets
# MAGIC - Stop querying and let serverless compute/your warehouse follow existing idle rules. Do not change shared
# MAGIC   warehouse settings. No schedule, subscription, job or endpoint was created by this module.
# MAGIC - Keep your own draft/space URLs or IDs in private notes. On resume, reload `_config`, review the view-write
# MAGIC   cell, reopen those **existing** assets, inspect sources, reset filters and compare with SQL. Do not create
# MAGIC   duplicate dashboards/spaces just because a notebook session restarted.
# MAGIC - For a partial build, record the last checkpoint. If only SQL ran, label D/G blocked, not complete.
# MAGIC - To delete UI assets, first open each recorded URL/ID, check it is **your** draft/space with the tagged title
# MAGIC   and exact source, then use its menu's **Move to trash / Delete** and confirm. Do not select by title alone,
# MAGIC   bulk-delete by prefix, or remove another learner's asset. If uncertain, stop rather than guessing.
# MAGIC - Also inspect the exact `dashboard_path` printed in section 3b. If a generated file remains in your own
# MAGIC   `a8learn` folder, move that file to trash. The hand-built draft, imported dashboard and generated file may
# MAGIC   be separate assets; check each one. Keep saved settings and the supplied Git template.
# MAGIC - `99_pause_and_cleanup` can drop your guarded `event_metrics` view along with other course UC objects.
# MAGIC   It does **not** delete dashboards, Genie spaces, conversations or caches. Delete your UI assets first if
# MAGIC   finishing; otherwise they remain but their queries break after the view is dropped. Deletion is not a
# MAGIC   secure-erasure claim; workspace retention applies. Saved settings and source notebooks remain.
# MAGIC - Return `create_reporting_view` to **no** when you finish.
# MAGIC
# MAGIC ### SQL-only fallback
# MAGIC If dashboards or Genie are unavailable, run the supplied SELECTs in the notebook/SQL editor and optionally
# MAGIC create a notebook bar chart from their results. If CREATE VIEW is blocked, use `display(spark.sql(metrics_sql))`
# MAGIC (a read, consuming compute) and use that SELECT as your reference without a saved view. Stop the cells that
# MAGIC depend on the view. This fallback proves SQL concepts only; it is **not** an AI response or dashboard.
# MAGIC Never work around a restriction by switching accounts, copying credentials or broadening data permissions.
# MAGIC
# MAGIC ### Recap, explain before you move on
# MAGIC - Why do separate pre-aggregations avoid double-counting? What grain reaches each dashboard widget?
# MAGIC - Why are SUM(rating_sum)/SUM(feedback_count) and AVG(average_rating) different?
# MAGIC - Why does a scheduled event have no attendance rate, even though it has confirmed tickets?
# MAGIC - What evidence would make you reject an eloquent Genie answer? Why is a filter not access control?
# MAGIC
# MAGIC **Completion requires:** SQL reconciliation and both exercises, observed dashboard checkpoint D, and
# MAGIC observed Genie checkpoint G, plus your explanations. Nothing automatically marks those UI checkpoints passed.
# MAGIC If blocked, keep the checkpoint and continue to Module 2 without claiming full completion.
# MAGIC **Next:** `01c_diagnostic_analytics`, explain why a difference exists. Then `02_governance`.
# MAGIC
# MAGIC ### Official references, checked 20 November 2026, not workspace acceptance
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)
# MAGIC - [Create a dashboard](https://docs.databricks.com/aws/en/dashboards/tutorials/create-dashboard)
# MAGIC - [Dashboard filters](https://docs.databricks.com/aws/en/dashboards/manage/filters)
# MAGIC - [Create a Genie Agent (formerly Space)](https://docs.databricks.com/aws/en/genie-agents/set-up)
# MAGIC - [Tune Genie with examples and instructions](https://docs.databricks.com/aws/en/genie-agents/tune-quality)
# MAGIC - [Genie testing and benchmarks](https://docs.databricks.com/aws/en/genie-agents/monitor)
