# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 13. Pipelines and jobs: keep the numbers fresh without rerunning a notebook
# MAGIC **Where this sits:** data engineering, and the fix for a problem the earlier modules left open. Module 1 loaded
# MAGIC the bookings once, so seats left stops being true the moment someone books after 20 November 2026. Module 12's
# MAGIC deployed agent had the same problem. Here, new bookings arrive as files, a **pipeline** cleans and counts them,
# MAGIC and a **job** runs it on a schedule.
# MAGIC
# MAGIC **Outcome:** land batches of new booking files in a volume, read the pipeline definition, create a **Lakeflow
# MAGIC Spark Declarative Pipeline** with three layers (bronze, silver, gold) and **data-quality rules**, run it, check
# MAGIC its numbers against an independent calculation, land a second batch and see that only the new file is
# MAGIC processed, then wrap the pipeline in a **scheduled job**, read the run history, and remove everything.
# MAGIC
# MAGIC **About 90 minutes, an estimate:** orient 10 · batches and the pipeline file 15 · create and run 25 (mostly
# MAGIC waiting) · second batch 10 · job 15 · exercises and recap 15.
# MAGIC **Before you start:** finish `00_setup` and `01_lakehouse_data`. All data is synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. Landing files and reading the pipeline need no cloud
# MAGIC action beyond writing to your volume. Creating and running the pipeline and job sit behind default-no
# MAGIC switches. If a step is blocked, finish the rest and repeat it in your paid workspace after running `00_setup`
# MAGIC and `01_lakehouse_data` there.
# MAGIC
# MAGIC **Cost boundary:** this lesson creates **one pipeline, one job and three tables**, and writes three small
# MAGIC files to your volume. Each pipeline update uses serverless compute for a minute or two, and uses quota on
# MAGIC Free or money on a paid workspace. The job's schedule is created **paused**, so nothing runs by itself. Delete
# MAGIC everything in the last section, or with `99_pause_and_cleanup`. This lesson was validated live on Free
# MAGIC Edition on 24 November 2026.
# MAGIC
# MAGIC ## Pipelines in plain English
# MAGIC A notebook runs the steps you wrote, in the order you wrote them, every time you press run. A **declarative
# MAGIC pipeline** is different: you describe what each table should contain, and Databricks decides the order, reads
# MAGIC only what is new, keeps track of what it has already seen, and records how many rows passed or failed each
# MAGIC quality rule. The common layout is three layers:
# MAGIC - **Bronze:** the new data exactly as it arrived, so you can always go back to it.
# MAGIC - **Silver:** the same data after rules have removed rows that should not be there.
# MAGIC - **Gold:** a table shaped for the question, here seats left per event.
# MAGIC
# MAGIC A **job** is a saved, schedulable run of one or more tasks. The task here refreshes the pipeline. Jobs add
# MAGIC what a notebook cannot: a schedule, retries, a history of every run and alerts.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Pipeline** | a set of table definitions Databricks keeps up to date |
# MAGIC | **Streaming table** | a table that reads each new input once, however often the pipeline runs |
# MAGIC | **Materialized view** | a stored query result the pipeline refreshes |
# MAGIC | **Bronze, silver, gold** | raw, cleaned and ready-to-use layers of the same data |
# MAGIC | **Expectation** | a data-quality rule on a table; here a failing row is dropped and counted |
# MAGIC | **Update** | one run of the pipeline |
# MAGIC | **Job** | a saved run of tasks, with a schedule and a history |
# MAGIC | **Idempotent** | running it twice gives the same result as running it once |
# MAGIC
# MAGIC **Business question for this lesson:** *how do we keep seats-left numbers current, and how do we know bad
# MAGIC bookings did not get counted?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Lakeflow Spark Declarative Pipelines](https://docs.databricks.com/aws/en/dlt/)
# MAGIC - [Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; batches makes the new booking files and the two lifecycle helpers find only your own objects.
import time
from pathlib import Path

from a8learn import batches
from a8learn.lifecycle import job_for_cleanup, pipeline_for_cleanup
from databricks.sdk import WorkspaceClient

# COMMAND ----------

# WHAT: checks the prerequisites and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming your pipeline, your job and the folder where new files will land.
A8.require("raw", "events", "bookings", "event_availability")
events, bookings, availability = A8.t("events"), A8.t("bookings"), A8.t("event_availability")
bronze, silver, gold = A8.t("bookings_bronze"), A8.t("bookings_clean"), A8.t("seats_live")
incoming = Path(A8.incoming_path)
w = WorkspaceClient()
print(f"Ready | pipeline {A8.pipeline_name} | job {A8.job_name} | files land in {incoming}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. The problem: a number that was true once
# MAGIC `event_availability` from Module 1 is a view over tables that nobody updates after the snapshot date. Real
# MAGIC bookings keep arriving. We simulate that with **batches**: small CSV files of new bookings, each fixed by its
# MAGIC number so every learner lands the same files. Each batch has 40 good rows and **three bad ones**: a ticket
# MAGIC count of zero or less, a status we do not use (`pending`) and a booking with no id.
# MAGIC
# MAGIC **Predict:** if the pipeline counts all 43 rows of a batch, will seats left be too high or too low? Which bad
# MAGIC row would do the most damage?

# COMMAND ----------

# WHAT: reads the scheduled events and the seats left today, before any new booking arrives.
# LOOK FOR: the number of scheduled events and three of their seat counts; these are the "before" numbers.
scheduled = [r["event_id"] for r in spark.sql(f"SELECT event_id FROM {events} WHERE status = 'scheduled'").collect()]
before = {r["event_id"]: int(r["available"]) for r in spark.sql(
    f"SELECT event_id, available FROM {availability}").collect()}
print(len(scheduled), "scheduled events; seats left before:", {e: before[e] for e in sorted(scheduled)[:3]})

# COMMAND ----------

# WHAT: defines the function that writes one batch file into your volume folder, unless it is already there.
# LOOK FOR: no output; a rerun never rewrites a file, so the pipeline never sees a changed file.
def land_batch(number):
    """Write batch ``number`` to the incoming folder (once) and return its rows."""
    rows = batches.new_batch(number, scheduled)
    target = incoming / f"bookings_batch_{number}.csv"
    if not target.exists():
        target.write_text(batches.to_csv(rows), encoding="utf-8")
    return rows

# COMMAND ----------

# WHAT: checks which course batches are already present, without overwriting or deleting retained files.
# LOOK FOR: no output; unfamiliar or edited CSV files stop the lesson rather than being silently counted.
def landed_batches():
    known = {incoming / f"bookings_batch_{n}.csv" for n in (1, 2, 3)}
    A8.expect(set(incoming.glob("*.csv")) <= known, "The incoming folder contains an unfamiliar CSV; inspect it first.")
    numbers = [n for n in (1, 2, 3) if (incoming / f"bookings_batch_{n}.csv").exists()]
    for number in numbers:
        text = (incoming / f"bookings_batch_{number}.csv").read_text(encoding="utf-8")
        A8.expect(text == batches.to_csv(batches.new_batch(number, scheduled)),
                  f"Batch {number} differs from the course fixture. Keep your file and use a fresh learner tag.")
    return numbers

# COMMAND ----------

# WHAT: lands batch 1 and shows the bad rows next to the first good ones.
# LOOK FOR: 43 rows in the file; the last three are the bad rows (zero or negative tickets, pending, no id).
A8.guard("raw")
incoming.mkdir(exist_ok=True)
batch1 = land_batch(1)
retained = landed_batches()
print(f"{len(batch1)} rows landed in {incoming.name}/bookings_batch_1.csv")
print("Batches already present:", retained, "(reruns reuse them; a new pipeline reads them all)")
for row in batch1[:2] + batch1[-3:]:
    print({k: row[k] for k in ("booking_id", "event_id", "tickets", "status")})

# COMMAND ----------

# WHAT: Check: the batch holds the expected counts of good and bad rows.
# LOOK FOR: two pass messages; these are the numbers the pipeline's quality rules must reproduce.
A8.expect(len(batch1) == batches.GOOD_ROWS + batches.BAD_ROWS, "Batch 1 has 43 rows.")
A8.expect(sum(batches.is_valid(r) for r in batch1) == batches.GOOD_ROWS, "Exactly 40 of them are valid.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Read the pipeline
# MAGIC The pipeline is one SQL file in your Git folder. It has three statements, one per layer. Read it before you
# MAGIC run it. **Look for:** the `STREAM` keyword that makes bronze read each file once; the three `CONSTRAINT` lines
# MAGIC that are the data-quality rules; and how gold adds the new confirmed tickets to the history in your
# MAGIC `bookings` table. The `${...}` names are **pipeline settings** that the next section fills in with your tag.

# COMMAND ----------

# WHAT: prints the pipeline definition.
# LOOK FOR: CREATE OR REFRESH STREAMING TABLE (bronze, silver) and MATERIALIZED VIEW (gold).
print((ROOT / "pipelines" / "a8_bookings.sql").read_text(encoding="utf-8"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Create the pipeline
# MAGIC The pipeline is created with the SDK from the file above. It is **serverless** (no cluster to manage),
# MAGIC **triggered** (it runs when asked, not continuously) and in **development** mode (quicker reruns while you
# MAGIC learn). Its settings carry your table names, your volume folder and your course marker. If a pipeline with your
# MAGIC name already exists and is yours it is reused; if it is not yours the lesson stops.
# MAGIC
# MAGIC Set `create_pipeline` to **yes** only if you accept the quota or cost. **If it differs:** a permission or
# MAGIC unsupported-feature message means this workspace cannot create pipelines; finish the rest and repeat the
# MAGIC step in your paid workspace. **Undo:** the last section, or `99_pause_and_cleanup`.

# COMMAND ----------

# WHAT: asks for your approval before a pipeline is created.
# LOOK FOR: a create_pipeline widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
create_approved = A8.gate("create_pipeline", "Create your bookings pipeline (uses compute when it runs)?")
print("Approved." if create_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: creates your pipeline, or finds the one you already created.
# LOOK FOR: a pipeline id and a link; nothing runs yet.
settings = {"a8_incoming": A8.incoming_path, "a8_events": events, "a8_bookings": bookings,
            "a8_bronze": A8.name("bookings_bronze"), "a8_silver": A8.name("bookings_clean"),
            "a8_gold": A8.name("seats_live"), **A8.course_tags}
pipeline_id = None
if create_approved:
    from databricks.sdk.service.pipelines import NotebookLibrary, PipelineLibrary

    existing = pipeline_for_cleanup(A8, w)  # refuses a pipeline with this name that is not yours
    if existing is not None:
        pipeline_id = existing.pipeline_id
        print("A pipeline with this name already exists and is yours; it was not changed.")
    else:
        pipeline_id = w.pipelines.create(
            name=A8.pipeline_name, catalog=A8.cfg.catalog, schema=A8.cfg.schema, serverless=True, continuous=False,
            development=True, configuration=settings,
            libraries=[PipelineLibrary(notebook=NotebookLibrary(path=str(ROOT / "pipelines" / "a8_bookings")))],
        ).pipeline_id
        print("Created pipeline", pipeline_id)
    A8.links(("Your pipeline: graph, events and data quality", "pipeline", pipeline_id))
else:
    print("Skipped. Reading the pipeline above is the core outcome; the rest needs this step.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Run it
# MAGIC One **update** reads batch 1, writes bronze, filters it into silver and rebuilds gold. We wait for it to
# MAGIC finish, then read what the pipeline recorded about each **expectation**: how many rows passed and how many
# MAGIC were dropped. Do not retry a failed update in a loop; open the pipeline page, read the error, then decide.
# MAGIC
# MAGIC **Predict:** how many rows will bronze hold, and how many will silver hold? Which rule drops which row?

# COMMAND ----------

# WHAT: asks for your approval before the pipeline runs.
# LOOK FOR: a run_pipeline widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
run_approved = A8.gate("run_pipeline", "Run your pipeline now (uses compute)?")
print("Approved." if run_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: defines how to run one update and wait for it, and how to read the quality counts it recorded.
# LOOK FOR: no output; refresh() returns the final state, and quality() lists passed and dropped rows per rule.
def refresh():
    update = w.pipelines.start_update(pipeline_id).update_id
    state = "RUNNING"
    for _ in range(60):  # about fifteen minutes at most
        time.sleep(15)
        state = w.pipelines.get_update(pipeline_id, update).update.state.value
        if state in {"COMPLETED", "FAILED", "CANCELED"}:
            break
    return state


def quality():
    """The latest passed and dropped counts per rule, read from the pipeline's event log."""
    events_reply = w.api_client.do("GET", f"/api/2.0/pipelines/{pipeline_id}/events",
                                   query={"max_results": "100", "order_by": "timestamp desc"})
    latest = {}
    for event in events_reply.get("events", []):
        if event.get("event_type") != "flow_progress":
            continue
        for rule in event.get("details", {}).get("flow_progress", {}).get("data_quality", {}).get(
                "expectations", []):
            latest.setdefault((rule["dataset"].split(".")[-1], rule["name"]),
                              (rule["passed_records"], rule["failed_records"]))
    return latest

# COMMAND ----------

# WHAT: runs the first update on batch 1 and waits for it to finish.
# LOOK FOR: COMPLETED after one to three minutes; any other state means open the pipeline page and read the error.
state_1 = None
if run_approved and pipeline_id is not None:
    state_1 = refresh()
    print("Update 1:", state_1)
elif run_approved:
    print("Create the pipeline first (section 3): there is nothing to run.")
else:
    print("Skipped: no update was run.")

# COMMAND ----------

# WHAT: counts the rows in each layer and shows the quality rules' counts.
# LOOK FOR: 43 bronze / 40 silver per landed batch, plus each rule's passed and dropped rows.
if state_1 == "COMPLETED":
    batch_numbers_1 = landed_batches()
    counts = {name: spark.table(table).count() for name, table in (("bronze", bronze), ("silver", silver),
                                                                   ("gold", gold))}
    print(counts)
    for (dataset, rule), (passed, failed) in sorted(quality().items()):
        print(f"{dataset:16} {rule:20} passed {passed:3}  dropped {failed}")
else:
    print("Skipped: the first update did not complete.")

# COMMAND ----------

# WHAT: Check: bronze kept every row, silver kept only the valid ones, and gold has a row per event.
# LOOK FOR: three pass messages; bronze keeping bad rows is deliberate, so you can always see what arrived.
if state_1 == "COMPLETED":
    A8.expect(counts["bronze"] == len(batch_numbers_1) * (batches.GOOD_ROWS + batches.BAD_ROWS),
              "Bronze holds every row from the landed batches, once.")
    A8.expect(counts["silver"] == len(batch_numbers_1) * batches.GOOD_ROWS, "Silver holds only the valid rows.")
    A8.expect(counts["gold"] == spark.table(events).count(), "Gold has one row per event.")
else:
    print("Skipped: nothing to check.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Check gold against an independent calculation
# MAGIC The pipeline says what seats are left. We should not just trust it. We work the answer out a different way:
# MAGIC take the seats left **before** (from Module 1's view), subtract the confirmed tickets in the valid rows of the
# MAGIC batch files, counted here in Python from the generator that wrote them. If the pipeline's gold table agrees for
# MAGIC every event, the layers, the rules and the join are all doing what we meant.

# COMMAND ----------

# WHAT: defines the expected seats left from the batch rows and the before numbers, then compares with gold.
# LOOK FOR: how many events changed, and one pass message that gold agrees on every event.
def expected_available(numbers):
    new = {}
    for number in numbers:
        for row in batches.new_batch(number, scheduled):
            if batches.is_valid(row) and row["status"] == "confirmed":
                new[row["event_id"]] = new.get(row["event_id"], 0) + int(row["tickets"])
    return {event: before[event] - new.get(event, 0) for event in before}, new


def gold_matches(numbers):
    expected, new = expected_available(numbers)
    rows = spark.sql(f"SELECT event_id, available FROM {gold}").collect()
    actual = {r["event_id"]: int(r["available"]) for r in rows}
    return actual == expected, len(new)

# COMMAND ----------

# WHAT: Check: gold's seats left equal the independent calculation for all batches present at update 1.
# LOOK FOR: one pass message; a mismatch means a bad row was counted or a good row was missed.
if state_1 == "COMPLETED":
    same, changed = gold_matches(batch_numbers_1)
    print(changed, "events have new bookings in batches", batch_numbers_1)
    A8.expect(same, "Gold's seats left equal the independent calculation for every event.")
else:
    print("Skipped: nothing to check.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. A second batch: only the new file is read
# MAGIC Now batch 2 arrives. We land it and run the pipeline again. A streaming table remembers which files it has
# MAGIC already processed, so on a clean run bronze grows by 43 rows (not by 86), and gold reflects both batches.
# MAGIC On a rerun batch 2 may already be present: then counts stay unchanged. Checks include all retained batches.
# MAGIC **Predict:** if you ran the pipeline a third time with no new file, what would change?

# COMMAND ----------

# WHAT: lands batch 2, runs a second update and counts the layers again.
# LOOK FOR: COMPLETED; on a clean run bronze 86 / silver 80, otherwise totals include retained batches.
state_2 = None
if state_1 == "COMPLETED":
    batch2 = land_batch(2)
    state_2 = refresh()
    batch_numbers_2 = landed_batches()
    print("Update 2:", state_2)
    if state_2 == "COMPLETED":
        print({name: spark.table(table).count() for name, table in (("bronze", bronze), ("silver", silver))},
              "source files:", spark.sql(f"SELECT count(DISTINCT source_file) AS n FROM {bronze}").first()["n"])
else:
    print("Skipped: the first update did not complete.")

# COMMAND ----------

# WHAT: Check: the second update counted each landed file once and gold agrees with those batches.
# LOOK FOR: four pass messages, including on reruns where batch 2 was already present.
if state_2 == "COMPLETED":
    A8.expect(spark.table(bronze).count() == len(batch_numbers_2) * (batches.GOOD_ROWS + batches.BAD_ROWS),
              "Bronze holds the landed files once, including any retained batches.")
    A8.expect(spark.table(silver).count() == len(batch_numbers_2) * batches.GOOD_ROWS,
              "Silver holds the valid rows from every landed batch.")
    A8.expect(spark.sql(f"SELECT count(DISTINCT source_file) AS n FROM {bronze}").first()["n"] == len(batch_numbers_2),
              "Bronze records which file each row came from.")
    A8.expect(gold_matches(batch_numbers_2)[0], "Gold agrees with the independent calculation for the landed batches.")
else:
    print("Skipped: the second update did not complete.")

# COMMAND ----------

# WHAT: compares today's seats left in Module 1's static view with the pipeline's gold table for the events that moved.
# LOOK FOR: three events where the static view is too high; that gap is the staleness the pipeline removes.
# A negative number means the event is oversold: the pipeline reports it rather than hiding it.
if state_2 == "COMPLETED":
    moved = spark.sql(f"""SELECT g.event_name, g.city, a.available AS static_view, g.available AS pipeline_gold
FROM {gold} g JOIN {availability} a ON g.event_id = a.event_id
WHERE g.available <> a.available AND g.status = 'scheduled' ORDER BY a.available - g.available DESC, g.event_id
LIMIT 3""").collect()
    for row in moved:
        print(f"{row['event_name']} ({row['city']}): static view {row['static_view']}, pipeline {row['pipeline_gold']}")
else:
    print("Skipped: nothing to compare.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Put it on a schedule with a job
# MAGIC Running the pipeline by hand is still manual. A **job** runs it for you. We create one job with one task, a
# MAGIC pipeline refresh, and a schedule (every morning at six) that we create **paused**, so nothing runs by
# MAGIC itself. The job is tagged as yours. Then we land batch 3 and run the job once, as the schedule would.
# MAGIC
# MAGIC Set `run_job` to **yes** only if you accept the quota or cost. A job run is another pipeline update.
# MAGIC **Undo:** the last section, or `99_pause_and_cleanup`.

# COMMAND ----------

# WHAT: asks for your approval before a job is created and run.
# LOOK FOR: a run_job widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
job_approved = A8.gate("run_job", "Create your refresh job and run it once (uses compute)?")
print("Approved." if job_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: creates your job with a paused schedule, lands batch 3 and runs the job once.
# LOOK FOR: a job id and a final state of SUCCESS for the run.
job_id, job_state = None, None
if job_approved and pipeline_id is not None:
    from databricks.sdk.service.jobs import CronSchedule, PauseStatus, PipelineTask, Task

    existing_job = job_for_cleanup(A8, w)  # refuses a job with this name that is not yours
    if existing_job is not None:
        job_id = existing_job.job_id
        print("A job with this name already exists and is yours; it was not changed.")
    else:
        job_id = w.jobs.create(
            name=A8.job_name, tags=A8.course_tags,
            tasks=[Task(task_key="refresh_bookings", pipeline_task=PipelineTask(pipeline_id=pipeline_id))],
            schedule=CronSchedule(quartz_cron_expression="0 0 6 * * ?", timezone_id="Europe/London",
                                  pause_status=PauseStatus.PAUSED)).job_id
        print("Created job", job_id, "with a paused schedule.")
    batch3 = land_batch(3)
    run_id = w.jobs.run_now(job_id).run_id
    for _ in range(60):
        time.sleep(15)
        run = w.jobs.get_run(run_id)
        if run.state.life_cycle_state.value in {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}:
            break
    job_state = run.state.result_state.value if run.state.result_state else run.state.life_cycle_state.value
    print("Job run:", job_state)
    A8.links(("Your job: runs, schedule and alerts", "job", job_id))
elif job_approved:
    print("Create the pipeline first (section 3): the job has nothing to refresh.")
else:
    print("Skipped. The pipeline above is the core outcome; a job adds the schedule and the history.")

# COMMAND ----------

# WHAT: Check: the job run succeeded and the pipeline picked up the third batch.
# LOOK FOR: two pass messages; bronze holds 43 rows per landed batch (129 on the full path).
if job_state is not None:
    batch_numbers_3 = landed_batches()
    A8.expect(job_state == "SUCCESS", "The job run succeeded.")
    A8.expect(spark.table(bronze).count() == len(batch_numbers_3) * (batches.GOOD_ROWS + batches.BAD_ROWS)
              and gold_matches(batch_numbers_3)[0], "The job refreshed the pipeline with every landed batch.")
else:
    print("Skipped: no job run to check.")

# COMMAND ----------

# WHAT: reads your job's runs from the system tables, which record every job and pipeline run in the workspace.
# LOOK FOR: your run, or a note that it has not appeared yet; system tables can lag by several minutes.
if job_id is not None:
    try:
        runs = spark.sql("""SELECT period_start_time, result_state FROM system.lakeflow.job_run_timeline
WHERE job_id = :job_id ORDER BY period_start_time DESC LIMIT 5""", args={"job_id": str(job_id)}).collect()
        print([(str(r["period_start_time"])[:19], r["result_state"]) for r in runs]
              or "No run is listed yet. System tables can lag; look again in a few minutes.")
    except Exception as error:  # the system schema may not be readable on every workspace
        print("System tables could not be read here:", type(error).__name__)
else:
    print("Skipped: no job.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Your turn
# MAGIC Three exercises on the tables the pipeline built. They need the pipeline to have run (section 4), but no model.
# MAGIC 1. Exercise 13.1: which events have the most new confirmed tickets in the cleaned bookings?
# MAGIC 2. Exercise 13.2: which scheduled events now have fewer than 30 seats left in the gold table?
# MAGIC 3. Exercise 13.3, a decision: which bronze rows does the pipeline refuse to count, and which rule refuses each?
# MAGIC
# MAGIC Use `IDENTIFIER(a8_bookings_bronze)`, `IDENTIFIER(a8_bookings_clean)` and `IDENTIFIER(a8_seats_live)` for the
# MAGIC table names. A blank answer shows the task and a hint. `A8.solution("13.1")` shows a worked answer. You can
# MAGIC also answer with a Spark or pandas DataFrame.

# COMMAND ----------

# WHAT: Check: compares your exercise 13.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query; skipped if the pipeline has not run.
answer_13_1 = """"""
if A8.exists("bookings_clean"):
    A8.check("13.1", answer_13_1)
else:
    print("Skipped: the cleaned bookings table does not exist yet. Run the pipeline in section 4 first.")

# COMMAND ----------

# WHAT: Check: compares your exercise 13.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query; skipped if the pipeline has not run.
answer_13_2 = """"""
if A8.exists("seats_live"):
    A8.check("13.2", answer_13_2)
else:
    print("Skipped: the gold table does not exist yet. Run the pipeline in section 4 first.")

# COMMAND ----------

# WHAT: Check: compares your exercise 13.3 answer (dropped rows and the rule each breaks) with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query; skipped if the pipeline has not run.
answer_13_3 = """"""
if A8.exists("bookings_bronze"):
    A8.check("13.3", answer_13_3)
else:
    print("Skipped: the bronze table does not exist yet. Run the pipeline in section 4 first.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Remove what you created
# MAGIC The pipeline and the job are what you pay for in quota or money, and deleting a pipeline does **not** delete
# MAGIC its tables, so we remove those too. Every delete checks that the object is yours: the job and the pipeline by
# MAGIC name, creator and course marker, the tables by owner and course comment. The batch files stay in your volume
# MAGIC until `99_pause_and_cleanup` removes the volume.
# MAGIC
# MAGIC **Undo:** to build it again, run sections 3 to 7 again.
# MAGIC Retained batches are read again by a new pipeline; the checks use all landed batches, not just batch 1.
# MAGIC **Continue to the app/evaluation:** leave this deletion switch at **no** to retain `seats_live` for Modules
# MAGIC 11, 14 and 15. Their setup prints whether it uses gold or the historical Module 1 view. If you delete gold,
# MAGIC they fall back to the historical view and cannot demonstrate freshness from these batches.

# COMMAND ----------

# WHAT: asks for your approval before deleting your job, pipeline and tables.
# LOOK FOR: a delete_pipeline_objects widget above the notebook, defaulting to no. Set it to yes, then rerun.
delete_approved = A8.gate("delete_pipeline_objects", "Delete your job, pipeline and pipeline tables?")
print("Approved." if delete_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: deletes your job, then your pipeline, then its three tables, only if you approved and they are yours.
# LOOK FOR: one line for each object removed, or a note that there was nothing to remove.
if delete_approved:
    removed = []
    for key in ("seats_live", "bookings_clean", "bookings_bronze"):  # preflight: stop before deleting anything
        if A8.exists(key):
            A8.guard(key)
    job_to_delete, pipeline_to_delete = job_for_cleanup(A8, w), pipeline_for_cleanup(A8, w)
    if job_to_delete is not None:
        w.jobs.delete(job_to_delete.job_id)
        removed.append("job")
    if pipeline_to_delete is not None:
        w.pipelines.delete(pipeline_to_delete.pipeline_id)
        removed.append("pipeline")
    for key in ("seats_live", "bookings_clean", "bookings_bronze"):
        if A8.exists(key):
            w.tables.delete(f"{A8.cfg.catalog}.{A8.cfg.schema}.{A8.name(key)}")
            removed.append(A8.name(key))
    print("Removed:", removed or "nothing; there was nothing of yours to remove.")
else:
    print("Not deleted. Run this section or 99_pause_and_cleanup before you finish.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 10. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: the pipeline dropped three bad rows per batch.
# MAGIC Who should find out about them, and what would you do if the dropped count suddenly jumped from three to
# MAGIC three hundred?
# MAGIC
# MAGIC **Completion requires:** all three exercises, the checks above, your explanations and, if you approved them, the
# MAGIC create, run and job steps and the deletion. Being blocked on a cloud step is fine: record it, and do not
# MAGIC count that outcome as complete.
# MAGIC
# MAGIC **Pause:** this lesson created a pipeline, a job, three tables and three small files. Delete them above;
# MAGIC `99_pause_and_cleanup` removes all of them.
# MAGIC **Next:** `11_interactive_app` (optional), then `99_pause_and_cleanup`.

# COMMAND ----------
# WHAT: asks why bad rows are kept in bronze but dropped from silver.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_13_a = """"""
A8.reflect("13.a", my_answer_13_a)

# COMMAND ----------
# WHAT: asks what a declarative pipeline gives you that a notebook rerun does not.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_13_b = """"""
A8.reflect("13.b", my_answer_13_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["New booking files landed in a volume, with deliberate bad rows",
              "A three-layer pipeline with data-quality rules, checked against an independent calculation",
              "A second batch processed incrementally, and a scheduled job with a run history",
              "A scoped removal of the job, the pipeline and its tables"],
             "11_interactive_app", "Share seats left with colleagues through an app")
