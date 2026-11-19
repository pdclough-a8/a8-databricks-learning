# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 2. Ask with evidence
# MAGIC **Outcome:** distinguish a supported answer from a confident guess.
# MAGIC Start with lesson 1 checked. Read `docs/lessons/02-model.md`.
# MAGIC We send the six CSV records in full. No retrieval, training or catalog connection is implied.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Prepare this notebook session
# MAGIC For the live code route, run the next two cells once on approved compute.
# MAGIC They install the pinned clients and restart Python, not a model request.
# MAGIC Skip both for simulation-only use. If package installation is blocked, use the UI route.

# COMMAND ----------
# MAGIC %pip install databricks-sdk==0.67.0 openai==2.14.0

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %run ./00_start_here

# COMMAND ----------
from logic import SYSTEM_PROMPT, answer_live, build_messages, simulate_answer
QUESTION = "Which events are in Leeds?"
print(simulate_answer(QUESTION, EVENTS))
print("SYSTEM PROMPT:\n" + SYSTEM_PROMPT)
print("USER MESSAGE FOR PLAYGROUND:\n" + build_messages(QUESTION, EVENTS)[1]["content"])

# COMMAND ----------
# MAGIC %md
# MAGIC ## One optional live request
# MAGIC A supplied serving endpoint, query permission, compatible chat model and budget are required.
# MAGIC UI route: copy the system/user messages above into AI Playground and send once.
# MAGIC Code route: enable the flag below and run this cell once, using notebook-user identity.
# MAGIC This request may bill. An enabled flag remains enabled in saved source: reset it immediately.

# COMMAND ----------
ALLOW_ONE_BILLABLE_REQUEST = False
if ALLOW_ONE_BILLABLE_REQUEST:
    from databricks.sdk import WorkspaceClient
    client = WorkspaceClient().serving_endpoints.get_open_ai_client().with_options(
        max_retries=0, timeout=45.0,
    )
    try:
        print(answer_live(client, ENDPOINT, QUESTION, EVENTS))
    except Exception:
        print("Request failed or returned no visible answer. Check model access with your instructor.")
else:
    print("No model called. Simulation does not satisfy the live-AI checkpoint.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Change, complete, transfer
# MAGIC 1. Predict the answer for Manchester with fewer than ten places. Change QUESTION.
# MAGIC 2. Complete: "An event fact is acceptable only when its ___ matches the ___ record."
# MAGIC 3. Independently ask for the cancellation policy. A supported answer admits the policy is absent.
# MAGIC For each approved request record expected facts, actual answer, IDs and pass/fail with a reason.
# MAGIC Reject invented dates or forecasts. A prompt is guidance, not a security boundary.
# MAGIC **Check:** Leeds E101=18/E104=22; Manchester under ten E102=3; policy unknown.
# MAGIC Reset the live flag to False, save your verdicts, then go to `03_deploy_assistant`.
