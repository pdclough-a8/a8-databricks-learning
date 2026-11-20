# Handover: next module, GenAI (Module 7)

Start a **fresh session** and invoke `/lean-databricks-module`. Read `AGENTS.md` and `docs/code-standard.md` first.
Agree outcomes, non-goals and a token budget before editing (about 300k suits a notebook, tests and docs). Do not use
subagents. This module involves model requests, so the cost and approval design below must be agreed before any code.

## State at handover
- Modules 0, 1, 3, 4, 6, 2, 3 and 99 are supplied. Last commit: `d13026f` (Module 6 plus Analytics8 logo), pushed to `main`.
- 3, 4 and 6 are offline checked only, **not live validated**. Open evidence gaps are in `docs/validation.md` and
  `docs/issues.md` (S18-S25). Do not claim live validation. Module 6 is the newest template for a read-only module.
- Final checks at 6: 79 unit tests pass (includes ruff); `mkdocs build --strict` passes. System Python lacks mkdocs, so
  run it with the repo's local packages: `$env:PYTHONPATH="<repo>\.packages"; python -m mkdocs build --strict`.
- Branding: the supplied Analytics8 logo is `docs/assets/a8-logo.png`, used on the docs site, README and START_HERE only.
  Notebooks keep text branding. It is not confirmed as the approved master (issue S25).

## Module to build: GenAI ("use a foundation model on our own data")
The curriculum row in `docs/index.md` reads: Playground, pay-per-token endpoints, `ai_query`, AI Functions for feedback,
prompts and tracing (Planned next). Suggested slice: **AI Functions over event feedback comments**, with the Playground as
a no-code first look. Defer tracing and prompt management if the budget is tight; confirm with the user.

## Reusable pieces
| Need | Existing object |
|---|---|
| Free-text comments with ratings | `feedback` table (Module 1): `feedback_id, event_id, booking_id, submitted_date, rating, comment`; 395 rows, synthetic |
| Event context | `events` table and `event_metrics` view (Module 3) |
| Opt-in gate pattern | `A8.gate(name, label)` in `lib/a8learn/__init__.py`; serving opt-in in `05_predictive_ml` |
| Ownership, checks, names | `A8.guard`, `A8.expect`, `A8.check`, `A8.require`, `A8.t`; `OBJECTS` registry; cleanup in `99_pause_and_cleanup` |
| Offline harness | `tests/test_descriptive.py` (OfflineSpark), `tests/test_diagnostic.py` and `tests/test_prescriptive.py` (args and `toPandas` wrapper) |

## Design points to agree with the user before editing
1. **Cost and approval (the main risk).** `ai_query` and AI Functions are billable model requests. `AGENTS.md` forbids paid
   model calls without explicit approval, and the tutor contract requires exact scope and cost risk first. Design: a
   gate defaulting to no, a **small fixed sample** (for example 5 to 10 comments, never the whole table by default), a
   printed row count and rough request count before running, and no loops that scale with table size.
2. **Which functions and endpoint.** Prefer built-in task functions (`ai_classify`, `ai_extract`, `ai_analyze_sentiment`,
   `ai_summarize`) before general `ai_query`. Confirm which are available and priced on Free Edition and on the paid
   workspace from current Databricks documentation; do not invent availability. Name the pay-per-token endpoint only
   after checking, and make it a variable the learner can change.
3. **Write boundary.** Prefer read-only with results held in memory, like 4 and 6. If a results table is wanted, make it
   an opt-in gated, guarded write registered in `OBJECTS`, with scoped cleanup in 99. Ask before adding.
4. **Evaluating the output.** Compare model labels with the human `rating` as a sanity check, state that ratings and
   comments both come from self-selected respondents, and include a human-reviewed checkpoint. Synthetic comments repeat
   a few templates, so say plainly that results will look cleaner than real feedback would.
5. **Concepts to separate (tutor contract).** Simulation versus AI, prompt context versus RAG (RAG is Module 5), and the
   notebook user's identity versus an app service principal (Module 11).
6. **Limits to state plainly.** Model output is non-deterministic and can be wrong; do not send personal or customer data
   (feedback is synthetic, never substitute real data); results are not live validated unless the user approves one run.
7. **Proposed non-goals:** no RAG or Vector Search, no agents or MCP, no custom serving endpoint, no fine-tuning, no
   scheduled jobs, no app, no writes to shared objects.

## Expected deliverables (mirror 4 and 6)
- `notebooks/07_genai.py` (number and name to confirm) with "Where this sits", Free Edition first, no cloud writes and
  no model requests by default.
- Two checked exercises in `lib/a8learn/exercises.py` that need no model call (for example SQL that builds the prompt
  input or validates a classification result against ratings), plus a human checkpoint for the model output.
- `tests/test_genai.py`: offline execution with the AI function **mocked or replaced by a deterministic stand-in**, so the
  suite never makes a model request; check the gate default, the sample-size cap and that no write or request happens
  when the gate is closed.
- Update `docs/index.md` (the GenAI row), `START_HERE.md`, the 6 "Next" line, `tests/test_stage1.py` notebook set,
  `docs/validation.md`, `docs/issues.md`, and `99_pause_and_cleanup` only if something is written.
- Run the unit suite and strict docs build **once** at completion. Commit and push only when the user says so.

## Pitfalls seen so far
- Ruff line limit is 120 (E501) and applies to notebooks, Markdown cells and `exercises.py`.
- Do not use bare `assert`; use `A8.expect`. Tests assert `AssertionError`, not `Exception` (B017).
- The offline adapter's `.first()` must return `None` for an empty result, as Spark does (fixed in `test_prescriptive.py`).
- Saved views cannot hold parameters; query values go in as `spark.sql(..., args={...})` named markers.
- Windows PowerShell 5.1 has no `&&`; Git LF-to-CRLF warnings are harmless; tail test output instead of dumping it.
- Scripts must call tools as `tools.<path>`; TodoWrite also goes through Script.
