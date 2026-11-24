# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 9. Agents: an assistant that chooses its own tools
# MAGIC **Where this sits:** generative AI that acts. Module 8b answered from documents. An **agent** goes one step
# MAGIC further: it decides which action to take (look up a document, check live seat numbers), reads the result and
# MAGIC decides what to do next.
# MAGIC
# MAGIC **Outcome:** build a small, safe **agent** for A8 Events customer questions. You write two **tools** (search
# MAGIC the knowledge base, check seats left), a **loop** that runs them with limits and a visible **trace**, a
# MAGIC **decider** that needs no model, then swap in a language model as the decider and score both on the same
# MAGIC tasks.
# MAGIC
# MAGIC **About 75 minutes, an estimate:** orient 10 · tools 20 · the loop 15 · model decider 15 · evaluation 10 ·
# MAGIC exercises and recap 5.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data` and `08b_rag` (it creates the chunk table the
# MAGIC search tool reads). All data is synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. The tools, the loop, the scripted decider, the
# MAGIC evaluation and the exercises need no model. The model decider sends a small number of chat requests behind a
# MAGIC default-no switch; if they are blocked, repeat that step in your paid workspace.
# MAGIC
# MAGIC **Cost boundary:** no table, endpoint or file is created. The tools only **read**. The model step sends at
# MAGIC most **12** short chat requests (a fixed budget in the code), plus an optional second set of at most 12
# MAGIC for native tool-calling. Inference uses quota on Free and can cost money
# MAGIC on a paid workspace.
# MAGIC
# MAGIC ## Agents in plain English
# MAGIC A customer writes: *is there space at the Analytics Breakfast, and can I bring a colleague instead of me?*
# MAGIC Two different things are needed: live seat numbers (from a table that changes every day) and a policy (from
# MAGIC a document). A model alone knows neither. An **agent** is a loop: the model reads the task, **chooses a tool**
# MAGIC and its inputs, we run the tool, the result goes back to the model, and it either chooses another tool or
# MAGIC writes the final answer.
# MAGIC
# MAGIC Because an agent acts, the safety design matters more than the cleverness: it may only use tools we list, the
# MAGIC tools here are read-only, every input is checked, the loop stops after a few steps, and every step is
# MAGIC recorded in a **trace** so you can see what it did and why.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Agent** | a loop in which a decider chooses actions, sees results and finishes with an answer |
# MAGIC | **Tool** | a function the agent may call, with a name, a description and checked inputs |
# MAGIC | **Decider** | what picks the next step: here a fixed set of rules, then a language model |
# MAGIC | **Trace** | the recorded list of steps: tool, inputs and result |
# MAGIC | **Guardrail** | a limit that holds even if the decider is wrong: allow-list, input checks, step cap |
# MAGIC | **Step cap** | the maximum number of tool calls before the loop stops |
# MAGIC | **Read-only** | the tool cannot change data, so a wrong choice cannot do damage |
# MAGIC
# MAGIC **Business question for this lesson:** *can an assistant answer both a policy question and a live seat-count
# MAGIC question correctly, and what stops it doing anything we did not intend?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Agent systems on Databricks](https://docs.databricks.com/aws/en/generative-ai/guide/agent-system-design-patterns)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; json reads the model's reply, re handles words and sql_string quotes text for SQL.
import json
import re
from collections import Counter

import numpy as np
from a8learn import sql_string
from databricks.sdk import WorkspaceClient

# COMMAND ----------

# WHAT: checks the prerequisites and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming the availability view, the chunk table and the chat endpoint.
A8.require("event_availability", "doc_chunks")
availability = A8.t("event_availability")
chunks_table = A8.t("doc_chunks")
CHAT_ENDPOINT = A8.cfg.chat_model or "databricks-meta-llama-3-3-70b-instruct"
print(f"Ready | {availability} | {chunks_table} | chat: {CHAT_ENDPOINT}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Two tools
# MAGIC A tool is an ordinary function. What makes it safe to give to an agent is what surrounds it. Ours are:
# MAGIC - **`search_docs(query)`**: finds the three knowledge-base sections closest in words to the query (the
# MAGIC   word-overlap search from 8b, reading your chunk table).
# MAGIC - **`check_availability(event_name)`**: reads the availability view from Module 1 and returns the scheduled
# MAGIC   events whose name contains the text, with seats left. The text travels as a **parameter**, never inside the
# MAGIC   SQL, so a customer cannot change the query.
# MAGIC
# MAGIC Both only read. **Predict:** the name "Practical GenAI Clinic" is the name of more than one scheduled event.
# MAGIC What should a good answer do about that?

# COMMAND ----------

# WHAT: loads the knowledge-base chunks into memory and defines the word-overlap search over them.
# LOOK FOR: no output; search_docs returns a list of sections, best first, each with its document name.
STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "and", "to", "of", "i", "my", "me", "do", "does", "can",
              "how", "what", "when", "where", "if", "it", "in", "on", "at", "for", "or", "you", "we", "our", "this",
              "that", "with", "there", "be", "will", "should", "get", "have", "has", "from", "by", "as"}
chunks = [row.asDict() if hasattr(row, "asDict") else dict(row) for row in spark.sql(
    f"SELECT doc_name, section, content FROM {chunks_table} ORDER BY doc_name, section").collect()]


def words(text):
    return Counter(w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP_WORDS)


def word_cosine(a, b):
    length = np.sqrt(sum(v * v for v in a.values())) * np.sqrt(sum(v * v for v in b.values()))
    return 0.0 if length == 0 else sum(a[w] * b[w] for w in a) / length


def search_docs(query):
    scored = sorted(((word_cosine(words(query), words(c["content"])), c) for c in chunks),
                    key=lambda s: s[0], reverse=True)[:3]
    return [{"doc_name": c["doc_name"], "section": c["section"], "score": round(score, 2), "text": c["content"]}
            for score, c in scored]

# COMMAND ----------

# WHAT: defines the seat-check tool as one read-only, parameterised query.
# LOOK FOR: no output; at most five scheduled events come back, soonest first, with seats left.
def check_availability(event_name):
    rows = spark.sql(f"""SELECT event_name, city, event_date, available FROM {availability}
WHERE status = 'scheduled' AND lower(event_name) LIKE :pattern ORDER BY event_date, city LIMIT 5""",
                     args={"pattern": f"%{event_name.lower().strip()}%"}).collect()
    return [{"event_name": r["event_name"], "city": r["city"], "event_date": str(r["event_date"]),
             "available": int(r["available"])} for r in rows]

# COMMAND ----------

# WHAT: tries each tool once on its own, before any agent exists.
# LOOK FOR: three document sections for the transfer question; the seats left for a single named event.
print([(r["doc_name"], r["section"], r["score"]) for r in search_docs("transfer my ticket to a colleague")])
print(check_availability("Pipelines in Practice"))

# COMMAND ----------

# WHAT: Check: both tools return the shape the agent expects.
# LOOK FOR: three pass messages; a failure means the earlier modules did not finish in this workspace.
A8.expect(len(search_docs("refund")) == 3, "search_docs returns three sections.")
A8.expect(len(check_availability("Practical GenAI Clinic")) > 1, "A shared event name returns several events.")
A8.expect(check_availability("no such event") == [], "An unknown event name returns an empty list, not an error.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Guardrails around the tools
# MAGIC The agent never calls a tool function directly. It calls `run_tool`, which enforces four rules whatever the
# MAGIC decider asks for:
# MAGIC 1. **Allow-list:** only the tools in `TOOLS` exist.
# MAGIC 2. **Input check:** exactly one text input, between 2 and 80 characters.
# MAGIC 3. **No exceptions escape:** a failure becomes an error message the decider can read, not a crash.
# MAGIC 4. **Read-only by construction:** neither tool contains a write.
# MAGIC
# MAGIC Each tool also has a **description**. The model decider reads these descriptions to choose, so they are part
# MAGIC of the design: a vague description gives wrong choices.

# COMMAND ----------

# WHAT: lists the allowed tools with the name of the one input each takes and a description for the decider.
# LOOK FOR: no output; TOOLS is the complete list of what the agent can do.
TOOLS = {
    "search_docs": {"function": search_docs, "input": "query",
                    "description": "Find sections of the A8 Events documents (booking, transfers, refunds, catering, "
                                   "accessibility, venues, online events). Use for policy and how-to questions."},
    "check_availability": {"function": check_availability, "input": "event_name",
                           "description": "Seats left for scheduled events whose name contains the text. Use for "
                                          "questions about space, capacity or whether an event is full."},
}


def run_tool(name, arguments):
    if name not in TOOLS:
        return {"error": f"Unknown tool {name!r}. Allowed: {sorted(TOOLS)}"}
    field = TOOLS[name]["input"]
    value = arguments.get(field) if isinstance(arguments, dict) else None
    if set(arguments) != {field} or not isinstance(value, str) or not 2 <= len(value.strip()) <= 80:
        return {"error": f"{name} takes one text input called {field!r}, 2 to 80 characters."}
    try:
        return {"result": TOOLS[name]["function"](value)}
    except Exception as error:  # the loop must survive a failing tool
        return {"error": f"{name} failed: {type(error).__name__}"}

# COMMAND ----------

# WHAT: Check: each guardrail refuses what it should and still allows a valid call.
# LOOK FOR: four pass messages.
A8.expect("error" in run_tool("delete_everything", {"query": "x"}), "A tool that is not on the list is refused.")
A8.expect("error" in run_tool("search_docs", {"query": "x"}), "A one-character input is refused.")
A8.expect("error" in run_tool("search_docs", {"query": "refund", "extra": "1"}), "An extra input is refused.")
A8.expect("result" in run_tool("check_availability", {"event_name": "Pipelines"}), "A valid call runs.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. The loop and its trace
# MAGIC The loop is short. Each round it asks the **decider** what to do. The decider returns either
# MAGIC `{"tool": name, "args": {...}}` or `{"final": "the answer"}`. A tool request is run through `run_tool` and
# MAGIC recorded in the **trace**. The loop stops when the decider gives a final answer, when it asks for something
# MAGIC invalid, or when it reaches the **step cap**. Here the cap is four tool calls.
# MAGIC
# MAGIC Any decider with the same shape plugs in, which is why we can test the loop with fixed rules first and a
# MAGIC model second.

# COMMAND ----------

# WHAT: defines the agent loop with its step cap and trace.
# LOOK FOR: no output; run_agent returns a status, the final answer and the trace of steps.
MAX_STEPS = 4


def run_agent(task, decide, max_steps=MAX_STEPS):
    trace = []
    for _ in range(max_steps + 1):
        decision = decide(task, trace)
        if "final" in decision:
            return {"status": "answered", "answer": str(decision["final"]), "trace": trace}
        if "tool" not in decision:
            return {"status": "stopped: " + decision.get("error", "invalid decision"), "answer": None, "trace": trace}
        if len(trace) == max_steps:
            return {"status": "stopped: step cap reached", "answer": None, "trace": trace}
        outcome = run_tool(decision["tool"], decision.get("args", {}))
        trace.append({"tool": decision["tool"], "args": decision.get("args", {}), **outcome})
    return {"status": "stopped: step cap reached", "answer": None, "trace": trace}

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. A decider with no model
# MAGIC Our first decider is a few rules. If the task names a scheduled event, check its seats. Otherwise search the
# MAGIC documents, and if no section matches well, say so. After one tool result it writes the final answer from that
# MAGIC result. It is not intelligent, but it shows everything an agent needs, and it gives the model a baseline to
# MAGIC beat.

# COMMAND ----------

# WHAT: defines the rule-based decider.
# LOOK FOR: no output; rules_decide(task, trace) returns the next decision for a task and its trace so far.
REFUSAL = "I can't find that in the A8 Events documents."
MIN_SCORE = 0.2
event_names = sorted({row["event_name"] for row in spark.sql(
    f"SELECT DISTINCT event_name FROM {availability} WHERE status = 'scheduled'").collect()})


def rules_decide(task, trace):
    if not trace:
        named = [n for n in event_names if n.lower() in task.lower()]
        return {"tool": "check_availability", "args": {"event_name": named[0]}} if named else \
               {"tool": "search_docs", "args": {"query": task}}
    last = trace[-1]
    if last["tool"] == "check_availability":
        rows = last.get("result") or []
        return {"final": "; ".join(f"{r['event_name']}, {r['city']}, {r['event_date']}: {r['available']} seats left"
                                   for r in rows) or "No scheduled event has that name."}
    best = (last.get("result") or [{"score": 0}])[0]
    return {"final": f"{best['text']} [{best['doc_name']}]" if best["score"] >= MIN_SCORE else REFUSAL}

# COMMAND ----------

# WHAT: runs the rule-based agent on one seat question and prints every step of its trace.
# LOOK FOR: one tool step, check_availability, then an answered status and a sentence built from the result.
outcome = run_agent("How many seats are left for Pipelines in Practice?", rules_decide)
for step in outcome["trace"]:
    print("STEP", step["tool"], step["args"], "->", step.get("result", step.get("error")))
print(outcome["status"], "|", outcome["answer"])

# COMMAND ----------

# WHAT: Check: the loop stops at the step cap even when the decider never finishes.
# LOOK FOR: two pass messages; a decider that keeps asking for tools cannot run forever.
endless = run_agent("anything", lambda task, trace: {"tool": "search_docs", "args": {"query": "refund"}})
A8.expect(endless["status"] == "stopped: step cap reached", "A decider that never finishes is stopped.")
A8.expect(len(endless["trace"]) == MAX_STEPS, f"The trace holds exactly {MAX_STEPS} tool calls.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. The tasks, and how to score an agent
# MAGIC Five customer tasks. For each we know which tool should be used and what a grounded answer must contain:
# MAGIC - the seat questions must give the **real number** from the view (we compute it separately, so the agent
# MAGIC   cannot mark its own work);
# MAGIC - the policy questions must **name the expected document** in the answer;
# MAGIC - the weather question has **no** tool that can answer it, so it is scored on refusing only.
# MAGIC
# MAGIC We report two scores: **tool choice** (did it use the right tool first? not scored for the weather task)
# MAGIC and **grounded** (is the answer supported by the data or documents?). Five tasks is a small test; it
# MAGIC compares deciders, it does not certify one.

# COMMAND ----------

# WHAT: defines the five tasks with the expected tool and the independently computed facts.
# LOOK FOR: no output; seats are read straight from the view, not from the agent.
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


def score(outcome, task):
    steps = outcome["trace"]
    right_tool = task["tool"] is None or (steps[0]["tool"] if steps else None) == task["tool"]
    if task["tool"] is None:  # nothing can answer it: the answer must be a refusal, not a guess
        grounded = bool(outcome["answer"]) and bool(re.search(r"can't|cannot|not find|don't|no information",
                                                              outcome["answer"].lower()))
    else:  # the answer must carry the real number, or name the right document
        grounded = bool(outcome["answer"]) and task["fact"] in outcome["answer"]
    return right_tool, grounded

# COMMAND ----------

# WHAT: runs the rule-based agent on all five tasks and scores it.
# LOOK FOR: one line per task with its status and the two scores; read the answers, not only the scores.
def evaluate(decide):
    results = []
    for task in TASKS:
        outcome = run_agent(task["task"], decide)
        results.append((task, outcome, *score(outcome, task)))
    return results


def report(name, results):
    for task, outcome, right_tool, grounded in results:
        print(f"{'ok ' if right_tool and grounded else 'MISS'} {task['task']} | {outcome['status']} | "
              f"tool {right_tool}, grounded {grounded}")
    print(f"{name}: tool choice {sum(r[2] for r in results)}/{len(results)}, "
          f"grounded {sum(r[3] for r in results)}/{len(results)}")


rules_results = evaluate(rules_decide)
report("Rules", rules_results)

# COMMAND ----------

# WHAT: Check: the rule-based agent finished every task inside the step cap.
# LOOK FOR: a pass message; scores below five are expected and are the baseline for the model.
A8.expect(all(outcome["status"] == "answered" for _, outcome, _, _ in rules_results),
          "Every task ended with an answer inside the step cap.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. A language model as the decider
# MAGIC Now the model chooses. The loop, the tools and the guardrails do not change; only `decide` does. The prompt
# MAGIC lists the tools with their descriptions, shows the task and the trace so far, and asks for **one JSON object
# MAGIC and nothing else**. If the reply is not valid JSON of the right shape, the loop stops with that reason rather
# MAGIC than guessing: a decider that cannot follow the format is not ready to act.
# MAGIC
# MAGIC A fixed **budget of 12 chat requests** covers the whole step, however the model behaves. Set the
# MAGIC `ask_agent` widget to **yes** only if you accept the quota or cost.
# MAGIC
# MAGIC **If it differs:** a message that a `databricks-` endpoint is not available means your workspace names
# MAGIC built-in models `system.ai.<model>`; put that name in `CHAT_ENDPOINT`. **Undo:** nothing is created.

# COMMAND ----------

# WHAT: defines the prompt, the reply parser and the model decider with its request budget.
# LOOK FOR: no output; parse_decision accepts only a final answer or an allowed tool request.
MAX_MODEL_CALLS = 12
model_calls = {"used": 0, "errors": []}


def build_agent_prompt(task, trace):
    tools = "\n".join(f"- {n}({t['input']}): {t['description']}" for n, t in TOOLS.items())
    seen = "\n".join(f"Step {i}: {s['tool']}({json.dumps(s['args'])}) -> "
                     f"{json.dumps(s.get('result', s.get('error')))[:900]}" for i, s in enumerate(trace, 1)) or "none"
    return ("You are an assistant for A8 Events customers. Use ONLY the tools below and what they return; "
            "never guess seat numbers or policies.\n"
            f"Tools:\n{tools}\n\nReply with ONE JSON object and nothing else, either "
            '{"tool": "<name>", "args": {"<input>": "<text>"}} to use a tool, or {"final": "<answer>"} when you can '
            f"answer. Cite document names. If no tool can answer, reply {{\"final\": \"{REFUSAL}\"}}.\n\n"
            f"Task: {task}\nSteps so far: {seen}")


def parse_decision(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        decision = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        decision = None
    if not isinstance(decision, dict):
        return {"error": "the reply was not valid JSON"}
    if "final" in decision:
        return {"final": decision["final"]}
    if "tool" in decision and isinstance(decision.get("args"), dict):
        return {"tool": decision["tool"], "args": decision["args"]}
    return {"error": "the reply had neither a final answer nor a tool request"}


def model_decide(task, trace):
    if model_calls["used"] >= MAX_MODEL_CALLS:
        return {"error": "the chat request budget is used up"}
    model_calls["used"] += 1
    reply = spark.sql(f"""SELECT ai_query({sql_string(CHAT_ENDPOINT)}, :prompt, failOnError => false,
modelParameters => named_struct('max_tokens', 300, 'temperature', CAST(0.0 AS DOUBLE))) AS reply""",
                      args={"prompt": build_agent_prompt(task, trace)}).collect()[0]["reply"]
    if reply["errorMessage"]:
        model_calls["errors"].append(reply["errorMessage"])
        return {"error": "the chat request failed"}
    return parse_decision(reply["result"])

# COMMAND ----------

# WHAT: Check: the parser accepts valid replies and rejects the rest, with no model request.
# LOOK FOR: four pass messages; model replies are untrusted text until they pass this parser and run_tool.
A8.expect(parse_decision('{"final": "ok"}') == {"final": "ok"}, "A final answer is accepted.")
A8.expect(parse_decision('```json\n{"tool": "search_docs", "args": {"query": "refund"}}\n```')["tool"] == "search_docs",
          "A tool request inside a code fence is accepted.")
A8.expect("error" in parse_decision("I think you should check availability"), "Plain text is rejected.")
A8.expect("error" in parse_decision('{"tool": "search_docs"}'), "A tool request without inputs is rejected.")

# COMMAND ----------

# WHAT: prints the prompt the model would see for the first step of the first task, without any model request.
# LOOK FOR: the two tools with their descriptions, the format instruction and the task; no data is included yet.
print(build_agent_prompt(TASKS[0]["task"], []))

# COMMAND ----------

# WHAT: asks for your approval before any chat request.
# LOOK FOR: an ask_agent widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
agent_approved = A8.gate("ask_agent", "Send up to 12 chat prompts (cost/quota)?")
print("Approved." if agent_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: runs the model-driven agent on the five tasks, within the request budget, and scores it.
# LOOK FOR: one line per task; compare with the rules baseline, and read the trace of any miss.
model_results = None
if agent_approved:
    model_results = evaluate(model_decide)
    report("Model", model_results)
    print(f"Chat requests used: {model_calls['used']} of {MAX_MODEL_CALLS}", model_calls["errors"][:1])
else:
    print("Model agent skipped. Everything above, and the exercises below, work without it.")

# COMMAND ----------

# WHAT: shows the model agent's answer and trace for each task, so you can judge them yourself.
# LOOK FOR: whether the answers quote the numbers and documents the tools returned, and whether the weather question
# is refused rather than answered.
if model_results is not None:
    for task, outcome, _, _ in model_results:
        print(f"TASK: {task['task']}\n  steps: {[(s['tool'], s['args']) for s in outcome['trace']]}\n"
              f"  {outcome['status']}: {outcome['answer']}\n")
else:
    print("Skipped: approve the model step above to see the answers.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Optional: the model's own tool-calling
# MAGIC Our decider asks for JSON in the prompt and parses it. Many chat models also have **native tool-calling**:
# MAGIC you send the tools as structured definitions and the model replies with a structured tool request, so no JSON
# MAGIC parsing from free text. This is the route production agents use. Not every endpoint supports it, and we have
# MAGIC **not confirmed it on Free Edition**, so this step is optional and reports plainly if it fails.
# MAGIC
# MAGIC The loop, tools, guardrails and scoring do not change; only the decider does. The call uses the endpoint's
# MAGIC OpenAI-compatible REST interface through the Databricks SDK (`api_client`), which needs no extra package. It
# MAGIC has its own budget of **12** requests and its own default-no switch.
# MAGIC
# MAGIC **If it differs:** an error about unknown fields or tools means this endpoint does not support tool-calling;
# MAGIC try another chat endpoint from your Serving page, or skip the step. **Undo:** nothing is created.

# COMMAND ----------

# WHAT: defines the tool descriptions in the standard function format, the conversation builder and the reply reader.
# LOOK FOR: no output; parse_native turns a structured reply into the same decision shape the loop already uses.
NATIVE_MAX_CALLS = 12
native_calls = {"used": 0, "errors": []}
TOOL_SPECS = [{"type": "function", "function": {
    "name": name, "description": tool["description"],
    "parameters": {"type": "object", "properties": {tool["input"]: {"type": "string"}},
                   "required": [tool["input"]]}}} for name, tool in TOOLS.items()]


def native_messages(task, trace):
    messages = [{"role": "system", "content": "You are an assistant for A8 Events customers. Use ONLY the tools and "
                 f"what they return; never guess. Cite document names. If no tool can answer, reply: {REFUSAL}"},
                {"role": "user", "content": task}]
    for i, step in enumerate(trace):
        messages.append({"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call_{i}", "type": "function",
            "function": {"name": step["tool"], "arguments": json.dumps(step["args"])}}]})
        messages.append({"role": "tool", "tool_call_id": f"call_{i}",
                         "content": json.dumps(step.get("result", step.get("error")))[:1500]})
    return messages


def parse_native(reply):
    try:
        message = reply["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {"error": "the reply had no message"}
    calls = message.get("tool_calls") or []
    if calls:
        try:
            return {"tool": calls[0]["function"]["name"], "args": json.loads(calls[0]["function"]["arguments"])}
        except (KeyError, TypeError, json.JSONDecodeError):
            return {"error": "the tool request was malformed"}
    return {"final": message.get("content") or ""}


def native_decide(task, trace):
    if native_calls["used"] >= NATIVE_MAX_CALLS:
        return {"error": "the native request budget is used up"}
    native_calls["used"] += 1
    body = {"messages": native_messages(task, trace), "tools": TOOL_SPECS, "max_tokens": 300, "temperature": 0.0}
    try:
        reply = WorkspaceClient().api_client.do("POST", f"/serving-endpoints/{CHAT_ENDPOINT}/invocations", body=body)
    except Exception as error:  # unsupported endpoint, quota or permissions: report it, do not crash
        native_calls["errors"].append(f"{type(error).__name__}: {str(error)[:200]}")
        return {"error": "the native request failed"}
    return parse_native(reply)

# COMMAND ----------

# WHAT: Check: the reply reader accepts a tool request and a final answer, and rejects a broken reply.
# LOOK FOR: three pass messages; no model request is sent.
A8.expect(parse_native({"choices": [{"message": {"tool_calls": [{"function": {
    "name": "search_docs", "arguments": '{"query": "refund"}'}}]}}]}) == {"tool": "search_docs",
                                                                       "args": {"query": "refund"}},
          "A structured tool request becomes a tool decision.")
A8.expect(parse_native({"choices": [{"message": {"content": "done"}}]}) == {"final": "done"},
          "A plain message becomes a final answer.")
A8.expect("error" in parse_native({"detail": "no"}), "A reply without a message is rejected.")

# COMMAND ----------

# WHAT: asks for your approval before any native tool-calling request.
# LOOK FOR: a native_tools widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
native_approved = A8.gate("native_tools", "Send up to 12 tool-calling requests (cost/quota)?")
print("Approved." if native_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: runs the same five tasks with native tool-calling and scores them against the other deciders.
# LOOK FOR: one line per task and the scores, or a plain note that this endpoint did not support it.
native_results = None
if native_approved:
    native_results = evaluate(native_decide)
    report("Native", native_results)
    print(f"Requests used: {native_calls['used']} of {NATIVE_MAX_CALLS}")
    if native_calls["errors"]:
        print("First error:", native_calls["errors"][0])
        print("Native tool-calling did not work on this endpoint; the JSON decider above is the fallback.")
else:
    print("Native tool-calling skipped. Nothing else depends on it.")

# COMMAND ----------
# MAGIC %md
# MAGIC Read the misses before trusting the scores. When the model gets a task wrong, find which part failed: the
# MAGIC **decision** (wrong tool or inputs), the **tool** (right call, poor result, as when word overlap ranks
# MAGIC the wrong section first for "take over my seat") or the **answer** (a good result written up badly). Each has
# MAGIC a different fix: a better description, a better tool, or a stricter prompt. The trace is how you find out.
# MAGIC
# MAGIC **What this is not yet:** this agent runs in your notebook. Putting an agent behind an endpoint, with
# MAGIC versions, access control and monitoring, is Module 12. The same tools and loop carry over, and so does the
# MAGIC native tool-calling you may have tried above.
# MAGIC
# MAGIC ## 8. Your turn
# MAGIC The seat tool runs one query. These two exercises are queries a tool like it could run, in SQL on the
# MAGIC availability view, and need **no model**.
# MAGIC 1. Exercise 9.1: scheduled events in London or Manchester with their seats left, fullest first.
# MAGIC 2. Exercise 9.2: for each city, how many scheduled events still have seats left?
# MAGIC
# MAGIC Use `IDENTIFIER(a8_event_availability)` for the view name. A blank answer shows the task and a hint.
# MAGIC `A8.solution("9.1")` shows a worked answer. You can also answer with a Spark or pandas DataFrame.

# COMMAND ----------

# WHAT: Check: compares your exercise 9.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_9_1 = """"""
A8.check("9.1", answer_9_1)

# COMMAND ----------

# WHAT: Check: compares your exercise 9.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_9_2 = """"""
A8.check("9.2", answer_9_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: which of the four guardrails would matter most
# MAGIC if you added a tool that could **cancel a booking**, and what extra control would you want first?
# MAGIC
# MAGIC **Completion requires:** both exercises, the checks above, your explanations and, if you approved it, the
# MAGIC model steps. Skipping or being blocked on a model step is fine: record it, and do not count that outcome as
# MAGIC complete.
# MAGIC
# MAGIC **Pause:** this lesson created nothing, so there is nothing extra to clean up.
# MAGIC **Next:** `99_pause_and_cleanup`.

# COMMAND ----------
# WHAT: asks why the agent calls tools through run_tool rather than directly.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_9_a = """"""
A8.reflect("9.a", my_answer_9_a)

# COMMAND ----------
# WHAT: asks what an agent can do that RAG from 8b cannot, and what it risks.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_9_b = """"""
A8.reflect("9.b", my_answer_9_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["Two read-only tools with checked inputs", "An agent loop with a step cap and a trace",
              "A rule-based decider as the baseline",
              "A model decider with a fixed request budget, scored on five tasks"],
             "12_deploy_and_govern", "Package, register, serve and govern the agent")
