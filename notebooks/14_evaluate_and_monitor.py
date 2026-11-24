# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 14. Evaluate and monitor: a release gate for the agent
# MAGIC **Where this sits:** the quality end of the operations modules. Module 9 built an agent and scored it by
# MAGIC hand. Module 12 packaged and served it. Neither answers the question a release manager asks: *is the new
# MAGIC version at least as good as the one running now, and can we prove it before we ship?* This module turns the
# MAGIC hand scoring into **MLflow evaluation** and uses it as a **release gate**.
# MAGIC
# MAGIC **Outcome:** define scoring rules that compare the agent's answers with facts read from your data, run them with
# MAGIC `mlflow.genai.evaluate()` as a **baseline** run, record **traces** of every tool call, run a worse **candidate**
# MAGIC (a model with last week's seat figures) and see the gate block it, release a refreshed one, read a monitoring
# MAGIC summary of the traces, and optionally add a model-based **judge** and test your Module 12 endpoint with the
# MAGIC same rules.
# MAGIC
# MAGIC **About 75 minutes, an estimate:** orient 10 · rules and tasks 15 · baseline and candidate runs 20 · traces
# MAGIC and monitoring 10 · optional judge and endpoint 10 · exercises and recap 10.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data` and `08b_rag` (the chunk table). `09_agents` and
# MAGIC `12_deploy_and_govern` are recommended; the endpoint section needs the endpoint from Module 12 to exist.
# MAGIC All data is synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. Reading the rules and scoring in plain Python need no
# MAGIC cloud action. Writing evaluation runs, the judge and the endpoint test each sit behind a default-no switch. If a
# MAGIC step is blocked, finish the rest and repeat it in your paid workspace after running `00_setup`,
# MAGIC `01_lakehouse_data` and `08b_rag` there.
# MAGIC
# MAGIC **Cost boundary:** this lesson creates **one MLflow experiment** holding three evaluation runs and their traces.
# MAGIC The scoring rules run in your notebook and make no model request. The optional judge makes **five** chat-model
# MAGIC requests (one per task) against your workspace's pay-per-token model, which uses quota on Free or money on a
# MAGIC paid workspace. The optional endpoint test sends five requests to an endpoint you already created in Module 12;
# MAGIC this lesson never creates or starts one. `99_pause_and_cleanup` removes the experiment. This lesson was
# MAGIC validated live on Free Edition on 24 November 2026, except the endpoint test, which was not run.
# MAGIC
# MAGIC ## Evaluation in plain English
# MAGIC Testing ordinary code is easy because the same input gives the same output. An agent's answers vary with its
# MAGIC data, its model and its prompt, so we test it the way a teacher marks coursework: a fixed set of questions, a
# MAGIC marking scheme, and a score we can compare from one version to the next. **Evaluation** is that marking.
# MAGIC **Tracing** is the record of how an answer was produced, so a failing mark can be traced back to the step that
# MAGIC caused it. **Monitoring** is marking again after release, on real traffic, to see quality drift.
# MAGIC
# MAGIC Two kinds of marker exist. A **code scorer** is a function you write: it checks something you can state
# MAGIC exactly, such as *does the answer carry the true seat number?* It is cheap, repeatable and cannot be talked
# MAGIC round. A **judge** is a language model given a rule in words, such as *only state what the documents say*. It
# MAGIC can read tone and meaning but it costs a model request, and its marks can vary. Use code scorers for facts and
# MAGIC judges for what only a reader can assess.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Evaluation set** | the fixed questions, each with the facts a good answer must contain |
# MAGIC | **Scorer** | a rule that marks one answer; the run reports the mean over all questions |
# MAGIC | **Judge** | a scorer that asks a language model to apply a written guideline |
# MAGIC | **Trace** | the recorded steps of one answer: the agent span and one span per tool call |
# MAGIC | **Baseline / candidate** | the version running now / the version someone wants to release |
# MAGIC | **Release gate** | a rule that blocks a candidate scoring worse than the baseline on any scorer |
# MAGIC | **Monitoring** | scoring and counting real traffic after release to see drift and failures |
# MAGIC
# MAGIC **Business question for this lesson:** *how do we know a change to the customer assistant has not made it
# MAGIC worse before customers see it?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Evaluate and monitor AI agents](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/)
# MAGIC - [MLflow tracing](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------
# MAGIC %md
# MAGIC **Install the MLflow version this lesson was written for.** `%pip install` installs packages **for this
# MAGIC notebook only**. The evaluation calls changed between MLflow versions, so we pin one. **Expect a red
# MAGIC `ERROR: pip's dependency resolver…` message:** the environment also contains `databricks-agents`, which wants a
# MAGIC newer MLflow. This lesson does not use it, so the message is harmless.

# COMMAND ----------
# MAGIC %pip install mlflow==3.6.0 typing_extensions==4.15.0

# COMMAND ----------

# WHAT: restarts this notebook's Python process so the pinned packages are the ones imported.
# LOOK FOR: no output. The next cell will print your catalog, schema and tag.
dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; agent_core is the packaged agent from Module 12 and evaluation holds the scoring rules.

import mlflow
import pandas as pd
from a8learn import agent_core, sql_string
from a8learn import evaluation as ev
from a8learn.lifecycle import endpoint_for_cleanup
from databricks.sdk import WorkspaceClient
from mlflow import MlflowClient
from mlflow.genai.scorers import Guidelines, scorer

# COMMAND ----------

# WHAT: checks the prerequisites and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming the source tables, the experiment path and the judge model.
availability_key = "seats_live" if spark.catalog.tableExists(A8.t("seats_live")) else "event_availability"
A8.require(availability_key, "doc_chunks")
availability = A8.t(availability_key)
spark.sql(f"DECLARE OR REPLACE VARIABLE a8_current_availability STRING DEFAULT {sql_string(availability)}")
chunks_table = A8.t("doc_chunks")
JUDGE_MODEL = A8.cfg.chat_model or "databricks-meta-llama-3-3-70b-instruct"
client = MlflowClient()
w = WorkspaceClient()
print(f"Ready | {availability} | {chunks_table} | experiment: {A8.evaluation_experiment_path} | judge: {JUDGE_MODEL}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. The evaluation set
# MAGIC The same five tasks as Modules 9 and 12, because a gate compares versions on a fixed set. For each task we
# MAGIC record the tool that should be used first and the **fact** a good answer must contain. The seat numbers are
# MAGIC read straight from your view, so the agent cannot mark its own work. Five tasks is a small set: it is enough
# MAGIC to show the mechanism and not enough to certify an agent.
# MAGIC
# MAGIC The agent under test is the packaged one from Module 12 (`agent_core`), answering from a **snapshot** of your
# MAGIC tables taken now. **I expect:** 32 chunks and 60 seat rows, as in Module 12.
# MAGIC Setup uses Module 13's `seats_live` if retained; otherwise it uses the historical `event_availability`.
# MAGIC The selected source also backs `IDENTIFIER(a8_current_availability)` in the exercise. Run Module 13 and
# MAGIC keep its tables to test real freshness. If data changes during this lesson, restart from setup.

# COMMAND ----------

# WHAT: takes the snapshot the baseline agent will answer from, as Module 12 did.
# LOOK FOR: the number of chunks and seat rows.
def take_snapshot():
    return {
        "taken_on": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "chunks": [{"doc_name": r["doc_name"], "section": r["section"], "content": r["content"]} for r in spark.sql(
            f"SELECT doc_name, section, content FROM {chunks_table} ORDER BY doc_name, section").collect()],
        "seats": [{"event_name": r["event_name"], "city": r["city"], "event_date": str(r["event_date"]),
                   "status": r["status"], "available": int(r["available"])} for r in spark.sql(
            f"SELECT event_name, city, event_date, status, available FROM {availability}").collect()],
    }


snapshot = take_snapshot()
print(f"{len(snapshot['chunks'])} chunks, {len(snapshot['seats'])} seat rows, taken {snapshot['taken_on']}")

# COMMAND ----------

# WHAT: defines the five tasks and builds the evaluation rows with their expected facts.
# LOOK FOR: five rows; each carries the question under inputs and the expected tool and fact under expectations.
def seats(event_name):
    return int(spark.sql(f"SELECT available FROM {availability} WHERE event_name = :n AND status = 'scheduled'",
                         args={"n": event_name}).collect()[0]["available"])


TASKS = [
    {"task": "How many seats are left for Pipelines in Practice?", "tool": "check_availability",
     "fact": str(seats("Pipelines in Practice"))},
    {"task": "Is there space at the Analytics Breakfast?", "tool": "check_availability",
     "fact": str(seats("Analytics Breakfast"))},
    {"task": "A colleague wants to take over my seat.", "tool": "search_docs", "fact": "booking-and-transfers.md"},
    {"task": "Do I get my money back if I pull out ten days before?", "tool": "search_docs",
     "fact": "cancellations-and-refunds.md"},
    {"task": "What is the weather forecast for the London event?", "tool": None, "fact": None},
]
EVAL_DATA = [{"inputs": {"question": t["task"]}, "expectations": ev.make_expectations(t["tool"], t["fact"])}
             for t in TASKS]
for row in EVAL_DATA:
    print(row["inputs"]["question"], "->", row["expectations"])

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Scoring rules
# MAGIC Three rules, written as ordinary functions in `lib/a8learn/evaluation.py` so they can be tested without MLflow:
# MAGIC - **right_tool:** the first tool used was the expected one (a task nothing can answer only needs a finish);
# MAGIC - **grounded:** the answer contains the true seat count followed by "seats left", or names the right document,
# MAGIC   or refuses when it should;
# MAGIC - **finished:** the agent ended with an answer inside its four-step cap.
# MAGIC
# MAGIC First we use them with no MLflow at all, to see exactly what they mark. **Predict:** how many of the five will
# MAGIC be grounded? Module 12's gate required at least four.

# COMMAND ----------

# WHAT: runs the agent on the five tasks and applies the three rules in plain Python.
# LOOK FOR: one line per task with the three marks, then the totals; MISS marks the tasks to read carefully.
plain = []
for row in EVAL_DATA:
    outputs = agent_core.answer(snapshot, row["inputs"]["question"])
    marks = (ev.right_tool(outputs, row["expectations"]), ev.grounded(outputs, row["expectations"]),
             ev.finished(outputs))
    plain.append(marks)
    print(f"{'ok  ' if all(marks) else 'MISS'} {row['inputs']['question']} | steps {outputs['steps']} | "
          f"tool {marks[0]}, grounded {marks[1]}, finished {marks[2]}")
print("Totals: tool", sum(m[0] for m in plain), "grounded", sum(m[1] for m in plain),
      "finished", sum(m[2] for m in plain))

# COMMAND ----------

# WHAT: Check: the rules mark the baseline agent as Module 12's gate expects.
# LOOK FOR: two pass messages; the stricter seat rule must not make the baseline worse than four of five.
A8.expect(sum(m[2] for m in plain) == len(TASKS), "Every task finished inside the step cap.")
A8.expect(sum(m[1] for m in plain) >= 4, "The baseline is grounded on at least four of five tasks.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Hand the rules to MLflow
# MAGIC `mlflow.genai.evaluate()` takes the evaluation rows, a function that answers a question, and a list of
# MAGIC scorers. It runs the function on every row, applies every scorer, and records the marks in an **MLflow run**
# MAGIC with a **trace** for every answer. The `@scorer` decorator turns each of our functions into a scorer. The
# MAGIC marks come back as a mean per scorer, named `grounded/mean` and so on.
# MAGIC
# MAGIC The function we pass is `predict(question)`. It is wrapped in a trace span called `support_agent`, and while
# MAGIC it runs each of the agent's two tools is wrapped in a span of its own, so a trace shows which tool was called.

# COMMAND ----------

# WHAT: defines the three scorers and the function that answers one question with a given snapshot.
# LOOK FOR: no output; nothing is written to MLflow until you approve the next section.
@scorer
def right_tool(outputs, expectations):
    return ev.right_tool(outputs, expectations)


@scorer
def grounded(outputs, expectations):
    return ev.grounded(outputs, expectations)


@scorer
def finished(outputs):
    return ev.finished(outputs)


SCORERS = [right_tool, grounded, finished]


def predict_with(snap):
    @mlflow.trace(name="support_agent", span_type="AGENT")
    def predict(question):
        return agent_core.answer(snap, question)
    return predict


def evaluate_agent(name, predict, scorers=None):
    """One evaluation run under the lesson's experiment, tagged as yours and named so the runs are easy to compare."""
    result = mlflow.genai.evaluate(data=EVAL_DATA, predict_fn=predict, scorers=scorers or SCORERS)
    for key, value in {**A8.course_tags, "mlflow.runName": name, "kind": "agent-evaluation"}.items():
        client.set_tag(result.run_id, key, value)
    return result


def means(result):
    return {k: float(v) for k, v in result.metrics.items() if k.endswith("/mean")}

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Baseline and candidate runs
# MAGIC This writes to MLflow: one experiment under your user folder and, for each run, a record with its marks and five
# MAGIC traces. Before writing we check the experiment is yours (a foreign one at the same path stops the lesson).
# MAGIC Every run carries your course tags so cleanup removes only yours.
# MAGIC
# MAGIC We run three versions:
# MAGIC 1. **baseline:** the agent as tested above, the version we would be running;
# MAGIC 2. **candidate:** the same code with a **stale snapshot**, every seat count out by seven, as if it had been
# MAGIC    logged a week ago. The answers are still fluent. **Predict:** which scorer notices, and which do not?
# MAGIC 3. **refreshed:** the snapshot taken again from the current data, as the Module 13 pipeline would allow.
# MAGIC
# MAGIC **If it differs:** a permission error naming your experiment means another course run uses your tag. **Undo:**
# MAGIC `99_pause_and_cleanup` deletes the experiment and its runs.

# COMMAND ----------

# WHAT: asks for your approval before anything is written to MLflow.
# LOOK FOR: a run_evaluation widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
evaluation_approved = A8.gate("run_evaluation", "Write evaluation runs and traces to your MLflow experiment?")
print("Approved." if evaluation_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: runs the baseline evaluation and prints its marks.
# LOOK FOR: three means; grounded should be 0.8 or higher and finished must be 1.0.
baseline = candidate = refreshed = experiment_id = None
if evaluation_approved:
    A8.claim_experiment(client, A8.evaluation_experiment_path)
    experiment = mlflow.set_experiment(A8.evaluation_experiment_path)
    A8.mark_experiment(client, experiment)
    experiment_id = experiment.experiment_id
    with ev.traced_tools(mlflow.trace):
        baseline_result = evaluate_agent("baseline", predict_with(snapshot))
    baseline = means(baseline_result)
    print("baseline:", baseline)
    A8.links(("Your evaluation experiment: runs and traces", "experiment", experiment_id))
else:
    print("Skipped. The plain-Python marks above are the core outcome; the MLflow runs need this step.")

# COMMAND ----------

# WHAT: Check: the baseline run finished every task and clears the floor.
# LOOK FOR: two pass messages.
if baseline is not None:
    A8.expect(baseline.get("finished/mean") == 1.0, "The baseline run finished every task.")
    A8.expect(baseline.get("grounded/mean", 0) >= 0.8, "The baseline run is grounded on at least four of five.")
else:
    print("Skipped: no baseline run.")

# COMMAND ----------

# WHAT: runs the stale-snapshot candidate and applies the release gate against the baseline.
# LOOK FOR: the candidate's means, then a gate verdict with the reasons; grounded should fall, finished should not.
if baseline is not None:
    with ev.traced_tools(mlflow.trace):
        candidate = means(evaluate_agent("candidate-stale-snapshot", predict_with(ev.stale_snapshot(snapshot))))
    verdict = ev.release_gate(baseline, candidate)
    print("candidate:", candidate)
    print("Gate:", "RELEASE" if verdict["passed"] else "BLOCKED", verdict["reasons"])
else:
    print("Skipped: no baseline run.")

# COMMAND ----------

# WHAT: Check: the gate blocks the stale candidate because of the grounded scorer.
# LOOK FOR: two pass messages; the answers finished and used the right tools, only the numbers were wrong.
if candidate is not None:
    A8.expect(not verdict["passed"], "The gate blocks a candidate whose seat figures are out of date.")
    A8.expect(candidate["finished/mean"] == 1.0 and candidate["grounded/mean"] < baseline["grounded/mean"],
              "It was blocked on grounded: the agent still finished every task.")
else:
    print("Skipped: no candidate run.")

# COMMAND ----------

# WHAT: runs a refreshed candidate (a snapshot taken again from the current tables) through the same gate.
# LOOK FOR: a RELEASE verdict with no reasons.
if baseline is not None:
    fresh = take_snapshot()
    with ev.traced_tools(mlflow.trace):
        refreshed = means(evaluate_agent("candidate-refreshed-snapshot", predict_with(fresh)))
    refreshed_verdict = ev.release_gate(baseline, refreshed)
    print("refreshed:", refreshed)
    print("Gate:", "RELEASE" if refreshed_verdict["passed"] else "BLOCKED", refreshed_verdict["reasons"])
    A8.expect(refreshed_verdict["passed"], "The gate releases a candidate that is no worse than the baseline.")
else:
    print("Skipped: no baseline run.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Read a trace
# MAGIC A trace is the evidence behind a mark. `mlflow.search_traces` returns them as a table, one row per answer.
# MAGIC Open one and list its **spans**: the first is the whole answer, the rest are the tool calls inside it. When a
# MAGIC question is marked wrong, the trace shows whether the agent chose the wrong tool, called the right one with a
# MAGIC bad input, or read the right result and still answered badly.
# MAGIC
# MAGIC The same traces are in the experiment page (the link above), under **Traces**, with their inputs and outputs.

# COMMAND ----------

# WHAT: loads the traces from your experiment and lists the spans of one answer.
# LOOK FOR: a support_agent span followed by one tool span, check_availability or search_docs.
traces = None
if experiment_id is not None:
    traces = mlflow.search_traces(locations=[experiment_id], max_results=50)
    print(f"{len(traces)} traces in the experiment")
    spans = []
    for trace_id in list(traces["trace_id"])[:5]:  # the table holds each trace as text, so fetch one to read its spans
        found = mlflow.get_trace(trace_id).data.spans
        if len(found) > 1:
            spans = found
            break
    print("Spans of one answer:", [(s.name, s.span_type) for s in spans] if spans else "none with tool spans")
else:
    print("Skipped: no evaluation experiment.")

# COMMAND ----------

# WHAT: Check: every answer was traced, and a trace contains a tool span.
# LOOK FOR: two pass messages; three runs of five tasks give at least fifteen traces.
if traces is not None:
    A8.expect(len(traces) >= 3 * len(TASKS), "Every answer from the three runs was traced.")
    A8.expect(bool(spans), "At least one trace contains a tool call span.")
else:
    print("Skipped: no traces.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Monitoring
# MAGIC Evaluation marks a fixed set before release. **Monitoring** watches what happens after: how many answers, how
# MAGIC many failed, how slow. The same traces answer those questions. Here we summarise yours in plain Python.
# MAGIC
# MAGIC **What this lesson does not do.** Databricks can also store production traces in Unity Catalog and run judges
# MAGIC over a sample of live traffic on a schedule, so quality is marked continuously. That needs a deployed
# MAGIC application that records traces and, for judges, paid model requests, so it is described here and not run. The
# MAGIC release gate you built above is the pre-release half; scheduled scoring of live traces is the post-release half.

# COMMAND ----------

# WHAT: counts the traces, the failures and the answer times in your experiment.
# LOOK FOR: failed 0; median and slowest times in milliseconds (these answers run in your notebook, so they are fast).
if traces is not None:
    summary = ev.trace_summary(zip(traces["state"], traces["execution_duration"], strict=True))
    print(summary)
    A8.expect(summary["failed"] == 0, "No traced answer failed.")
else:
    print("Skipped: no traces.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Optional: a judge for what a number cannot show
# MAGIC The code scorers check facts. They cannot tell whether an answer is *supported* by the documents or whether it
# MAGIC refuses politely. A **judge** applies a rule written in words. We use MLflow's `Guidelines` judge with the
# MAGIC chat model named in your settings, run on the five baseline answers: **five model requests**, which use quota
# MAGIC on Free or money on a paid workspace.
# MAGIC
# MAGIC Judges are marked by a model, so the same answer can score differently on another day, and a judge is only as
# MAGIC good as its guideline. Treat its mark as a second opinion to read, not as a gate on its own.
# MAGIC
# MAGIC **If it differs:** a message that the endpoint is not available means your workspace names its models
# MAGIC differently; set `chat_model` in `00_setup`.

# COMMAND ----------

# WHAT: asks for your approval before making the five judge requests.
# LOOK FOR: a run_judge widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
judge_approved = A8.gate("run_judge", "Run a model-based judge on five answers (five chat-model requests)?")
print("Approved." if judge_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: runs the judge on the baseline agent's answers and prints its mean mark.
# LOOK FOR: supported_answers/mean between 0 and 1; open the run's Evaluation tab to read the judge's reasons.
if judge_approved and baseline is not None:
    supported = Guidelines(
        name="supported_answers", model=f"databricks:/{JUDGE_MODEL}",
        guidelines="The answer states only facts that come from the A8 Events documents or seat figures, and says it "
                   "cannot help when the question is outside them. It does not invent policies, prices or forecasts.")
    with ev.traced_tools(mlflow.trace):
        judged = means(evaluate_agent("judge-baseline", predict_with(snapshot), scorers=[supported]))
    print("judge:", judged)
    A8.expect(0.0 <= judged["supported_answers/mean"] <= 1.0, "The judge returned a mark for the answers.")
elif judge_approved:
    print("Skipped: run the baseline first.")
else:
    print("Skipped: no judge requests were made.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Optional: test your deployed endpoint with the same rules
# MAGIC The gate is most useful on what is actually running. If you served the agent in Module 12 and have not deleted
# MAGIC the endpoint, we send the five questions to it and apply the same rules. **This lesson does not create or
# MAGIC start an endpoint**: if yours is absent it says so and moves on.
# MAGIC
# MAGIC **Predict:** will the endpoint pass the gate? Its snapshot was taken when you logged the model in Module 12. If
# MAGIC bookings have changed since, for example after Module 13, its seat figures are out of date and the gate should
# MAGIC say so. That is the gate working, not a fault.

# COMMAND ----------

# WHAT: asks for your approval before sending five requests to your existing endpoint.
# LOOK FOR: an evaluate_endpoint widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
endpoint_approved = A8.gate("evaluate_endpoint", "Send five questions to your Module 12 agent endpoint?")
print("Approved." if endpoint_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: evaluates the deployed endpoint with the same scorers and applies the gate against the baseline.
# LOOK FOR: the endpoint's means and a gate verdict; BLOCKED with a grounded reason means its snapshot is out of date.
endpoint_means = None
if endpoint_approved and baseline is not None:
    if endpoint_for_cleanup(A8, w, A8.agent_endpoint_name) is None:
        print("There is no agent endpoint of yours to test. Serve one in Module 12 first.")
    else:
        def predict_endpoint(question):
            reply = w.api_client.do("POST", f"/serving-endpoints/{A8.agent_endpoint_name}/invocations",
                                    body={"dataframe_records": [{"question": question}]})
            prediction = reply["predictions"][0]
            return {"answer": prediction["answer"], "status": prediction["status"],
                    "steps": [s for s in prediction["steps"].split(",") if s]}

        endpoint_means = means(evaluate_agent("endpoint", predict_endpoint))
        endpoint_verdict = ev.release_gate(baseline, endpoint_means)
        print("endpoint:", endpoint_means)
        print("Gate:", "RELEASE" if endpoint_verdict["passed"] else "BLOCKED", endpoint_verdict["reasons"])
elif endpoint_approved:
    print("Skipped: run the baseline first.")
else:
    print("Skipped: no requests were sent.")

# COMMAND ----------

# WHAT: Check: the endpoint answered every question.
# LOOK FOR: one pass message; whether it passed the gate is for you to read above, not a failure of the lesson.
if endpoint_means is not None:
    A8.expect(endpoint_means["finished/mean"] == 1.0, "The endpoint answered every task inside the step cap.")
else:
    print("Skipped: no endpoint results.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Your turn
# MAGIC The expected values come from your data, not from the agent. The first exercise builds them; the second asks
# MAGIC you to make the release decision yourself:
# MAGIC 1. Exercise 14.1: the true seat counts for the two seat questions, as a table.
# MAGIC 2. Exercise 14.2, a decision: write your own release gate, `my_gate`, for a stricter policy. It is run against
# MAGIC    eight supplied situations (no cloud calls), and a wrong decision is explained case by case.
# MAGIC
# MAGIC Use `IDENTIFIER(a8_current_availability)` for the selected source. A blank answer shows the task and a hint.
# MAGIC `A8.solution("14.1")` or `A8.solution("14.2")` shows a worked answer. You can also answer 14.1 with a Spark or
# MAGIC pandas DataFrame.

# COMMAND ----------

# WHAT: Check: compares your exercise 14.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_14_1 = """"""
A8.check("14.1", answer_14_1)

# COMMAND ----------

# WHAT: Check: runs your release gate against eight supplied baseline and candidate marks.
# LOOK FOR: the task while the body is `...`; otherwise "correct on all 8 cases" or the first case it decides wrongly.
def my_gate(baseline, candidate):
    ...  # your rule here: return True to release, False to block


A8.check_rule("14.2", my_gate)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 10. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: which of the five tasks would you add first if
# MAGIC a customer complained, and what would its expected fact be?
# MAGIC
# MAGIC **Completion requires:** the exercises, the checks above, your explanations and, if you approved them, the
# MAGIC evaluation runs. Being blocked on a cloud step is fine: record it, and do not count that outcome as complete.
# MAGIC
# MAGIC **Pause:** this lesson created one MLflow experiment with three runs (four with the judge, five with the
# MAGIC endpoint). It costs nothing to keep; `99_pause_and_cleanup` deletes it.
# MAGIC **Next:** `15_release_and_rollback`.

# COMMAND ----------
# WHAT: asks which scorer catches stale numbers and why a wording-only judge would not.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_14_a = """"""
A8.reflect("14.a", my_answer_14_a)

# COMMAND ----------
# WHAT: asks why a candidate is compared with a baseline instead of a fixed pass mark.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_14_b = """"""
A8.reflect("14.b", my_answer_14_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["Scoring rules that compare answers with facts read from your data",
              "MLflow evaluation runs with traces, and a release gate against a baseline",
              "A stale candidate blocked, a refreshed one released",
              "A monitoring summary of traces, an optional judge and an optional endpoint test"],
             "15_release_and_rollback", "Release a new agent version through the gate, and roll it back")
