"""Plain-Python pieces of Module 14: scoring rules, a stale-snapshot candidate, the release gate and a trace summary.

Nothing here imports MLflow at module level, so the rules can be tested offline. The notebook wraps the scoring
functions with MLflow's @scorer and passes them to mlflow.genai.evaluate.
"""
import re
import statistics
from contextlib import contextmanager

from . import agent_core

REFUSAL_WORDS = re.compile(r"can't|cannot|not find|don't|no information")


def make_expectations(task, fact):
    """Expectations for one row. Strings only: empty text means 'no tool can answer this, it must refuse'."""
    return {"expected_tool": task or "none", "fact": fact or ""}


def right_tool(outputs, expectations):
    """True when the first tool used is the expected one (a refusal task only needs the agent to finish)."""
    if expectations["expected_tool"] == "none":
        return True
    steps = _steps(outputs)
    return bool(steps) and steps[0] == expectations["expected_tool"]


def grounded(outputs, expectations):
    """True when the answer carries the real seat count, names the right document, or refuses when it should."""
    text = str(outputs.get("answer", ""))
    if expectations["expected_tool"] == "none":
        return bool(REFUSAL_WORDS.search(text.lower()))
    fact = expectations["fact"]
    if expectations["expected_tool"] == "check_availability":  # whole number followed by "seats left", not a substring
        return bool(re.search(rf"(?<!\d){re.escape(fact)} seats left", text))
    return fact in text


def finished(outputs):
    """True when the agent ended with an answer inside its step cap."""
    return outputs.get("status") == "answered"


def _steps(outputs):
    steps = outputs.get("steps", [])
    return [s for s in steps.split(",") if s] if isinstance(steps, str) else list(steps)


def stale_snapshot(snapshot, shift=7):
    """A copy of the snapshot with every seat count wrong by `shift`: last week's figures, as a release candidate."""
    return {**snapshot, "seats": [{**r, "available": r["available"] + shift} for r in snapshot["seats"]]}


@contextmanager
def traced_tools(trace):
    """Wrap each agent tool in an MLflow span for the duration of the block, then restore the originals.

    `trace` is mlflow.trace. Spans nest under whatever traced function is running when run_tool calls the tool.
    """
    original = dict(agent_core.TOOLS)
    try:
        for name, (field, function) in original.items():
            agent_core.TOOLS[name] = (field, trace(name=name, span_type="TOOL")(function))
        yield
    finally:
        agent_core.TOOLS.clear()
        agent_core.TOOLS.update(original)


def release_gate(baseline, candidate, tolerance=0.0, required=("finished/mean",)):
    """Decide whether a candidate may be released. Metrics are MLflow's `{scorer}/mean` values.

    The candidate fails if any metric is lower than the baseline's by more than `tolerance`, or if a metric in
    `required` is below 1.0. Returns {"passed": bool, "reasons": [...]}; a missing metric counts as a failure.
    """
    reasons = []
    for name, base in sorted(baseline.items()):
        if name not in candidate:
            reasons.append(f"{name} is missing from the candidate run")
        elif candidate[name] < base - tolerance:
            reasons.append(f"{name} fell from {base:.2f} to {candidate[name]:.2f}")
    for name in required:
        if candidate.get(name, 0.0) < 1.0 and not any(r.startswith(name) for r in reasons):
            reasons.append(f"{name} is {candidate.get(name, 0.0):.2f}, it must be 1.00")
    return {"passed": not reasons, "reasons": reasons}


def trace_summary(rows):
    """Summarise traces: how many, how many failed, median and slowest duration in ms.

    `rows` is any iterable of (state, duration_ms) pairs, for example from a search_traces table.
    """
    rows = list(rows)
    durations = sorted(float(d) for _, d in rows if d is not None)
    failed = sum(1 for state, _ in rows if str(state).split(".")[-1].upper() == "ERROR")
    return {"traces": len(rows), "failed": failed,
            "median_ms": round(statistics.median(durations), 1) if durations else None,
            "slowest_ms": round(durations[-1], 1) if durations else None}
