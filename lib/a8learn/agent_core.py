"""The A8 Events support agent from Module 9, packaged as plain code that can be logged and served.

It has no Spark, no network and no credentials. Everything it knows is in a snapshot dictionary
({"chunks": [...], "seats": [...]}) saved with the model, so a served copy answers from the data as it was when the
model was logged. The decider is the rule-based one from Module 9: a served model cannot call another endpoint
without extra authentication set-up, which this course does not attempt on Free Edition.
"""
import math
import re
from collections import Counter

REFUSAL = "I can't find that in the A8 Events documents."
MAX_STEPS = 4
MIN_SCORE = 0.2
STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "and", "to", "of", "i", "my", "me", "do", "does", "can",
              "how", "what", "when", "where", "if", "it", "in", "on", "at", "for", "or", "you", "we", "our", "this",
              "that", "with", "there", "be", "will", "should", "get", "have", "has", "from", "by", "as"}


def words(text):
    return Counter(w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP_WORDS)


def word_cosine(a, b):
    length = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return 0.0 if length == 0 else sum(a[w] * b[w] for w in a) / length


def search_docs(snapshot, query):
    scored = sorted(((word_cosine(words(query), words(c["content"])), c) for c in snapshot["chunks"]),
                    key=lambda s: s[0], reverse=True)[:3]
    return [{"doc_name": c["doc_name"], "section": c["section"], "score": round(score, 2), "text": c["content"]}
            for score, c in scored]


def check_availability(snapshot, event_name):
    needle = event_name.lower().strip()
    rows = [r for r in snapshot["seats"] if r["status"] == "scheduled" and needle in r["event_name"].lower()]
    rows.sort(key=lambda r: (r["event_date"], r["city"]))
    return [{"event_name": r["event_name"], "city": r["city"], "event_date": str(r["event_date"]),
             "available": int(r["available"])} for r in rows[:5]]


TOOLS = {"search_docs": ("query", search_docs), "check_availability": ("event_name", check_availability)}


def run_tool(snapshot, name, arguments):
    if name not in TOOLS:
        return {"error": f"Unknown tool {name!r}. Allowed: {sorted(TOOLS)}"}
    field, function = TOOLS[name]
    value = arguments.get(field) if isinstance(arguments, dict) else None
    if set(arguments) != {field} or not isinstance(value, str) or not 2 <= len(value.strip()) <= 80:
        return {"error": f"{name} takes one text input called {field!r}, 2 to 80 characters."}
    try:
        return {"result": function(snapshot, value)}
    except Exception as error:  # the loop must survive a failing tool
        return {"error": f"{name} failed: {type(error).__name__}"}


def rules_decide(snapshot, task, trace):
    if not trace:
        names = sorted({r["event_name"] for r in snapshot["seats"] if r["status"] == "scheduled"})
        named = [n for n in names if n.lower() in task.lower()]
        return {"tool": "check_availability", "args": {"event_name": named[0]}} if named else \
               {"tool": "search_docs", "args": {"query": task}}
    last = trace[-1]
    if last["tool"] == "check_availability":
        rows = last.get("result") or []
        return {"final": "; ".join(f"{r['event_name']}, {r['city']}, {r['event_date']}: {r['available']} seats left"
                                   for r in rows) or "No scheduled event has that name."}
    best = (last.get("result") or [{"score": 0}])[0]
    return {"final": f"{best['text']} [{best['doc_name']}]" if best["score"] >= MIN_SCORE else REFUSAL}


def answer(snapshot, task, max_steps=MAX_STEPS):
    """Run the agent loop on one task and return {"status", "answer", "steps"}; steps are the tool names used."""
    trace = []
    for _ in range(max_steps + 1):
        decision = rules_decide(snapshot, task, trace)
        if "final" in decision:
            return {"status": "answered", "answer": str(decision["final"]), "steps": [s["tool"] for s in trace]}
        if len(trace) == max_steps:
            break
        trace.append({"tool": decision["tool"], "args": decision["args"],
                      **run_tool(snapshot, decision["tool"], decision["args"])})
    return {"status": "stopped: step cap reached", "answer": "", "steps": [s["tool"] for s in trace]}
