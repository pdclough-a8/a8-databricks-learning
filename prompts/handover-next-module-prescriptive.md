# Handover: next module, prescriptive analytics

Start a **fresh session** and invoke `/lean-databricks-module`. Read `AGENTS.md` and `docs/code-standard.md` first.
Agree outcomes, non-goals and a token budget (about 300k agreed) before editing. Do not use subagents.

## State at handover
- Modules 0, 1, 1b, 1c, 2, 3 and 99 are supplied. 1b and 1c are offline checked only, **not live validated**.
- Module 1c (`notebooks/01c_diagnostic_analytics.py`, `tests/test_diagnostic.py`, exercises `1c.1`, `1c.2`) is the
  template for a read-only analytical module: it reads `event_metrics`, writes nothing, has seeded numpy code,
  independent-Python test oracles and a human-reviewed Genie checkpoint.
- Final checks at 1c: 65 unit tests pass (includes ruff); `mkdocs build --strict` passes (run from a venv with
  `mkdocs-material==9.6.21`; system Python 3.14 lacked mkdocs).
- Open evidence gaps are in `docs/validation.md` and `docs/issues.md` (S18-S23). Do not claim live validation.

## Module to build: prescriptive analytics ("what should we do?")
Covers **overbooking and catering decisions**, what-if analysis, Monte Carlo simulation and simple optimisation over
Module 3's predictions. About 300k tokens. Suggested number: 1d or 4-shifted; confirm with the user and update
`docs/index.md` (the Prescriptive row is currently "number to be assigned, Planned").

## Reusable pieces
| Need | Existing object |
|---|---|
| Per-booking attendance probability, `model_version`, `scored_at` | `attendance_predictions` table (Module 3) |
| Expected attendance per event and capacity | `event_forecast` view (Module 3), `event_availability` view (Module 1) |
| Event-grain metrics, ticket-weighted attendance | `event_metrics` view (Module 1b) |
| Latest prediction per booking | Exercise `3.1` pattern: row_number() over booking_id by scored_at desc |
| Gates, ownership, checks | `A8.gate`, `A8.guard`, `A8.expect`, `A8.check`, `A8.require` |
| Object registry | `OBJECTS` in `lib/a8learn/__init__.py`; cleanup in `99_pause_and_cleanup` |
| Offline test harness | `tests/test_descriptive.py` (OfflineSpark, independent_metrics), `tests/test_diagnostic.py` |

## Design points to agree with the user before editing
1. **Decisions and objectives:** overbooking (how many extra tickets to sell given no-show probability, cost of a
   turned-away attendee versus an empty seat) and catering (how many portions to order given uncertain attendance, cost
   of shortfall versus waste). State costs as clearly labelled **assumed teaching parameters**; there is no payment
   ledger, so no revenue or real cost claims.
2. **Uncertainty:** treat bookings as independent Bernoulli draws with the model probability (an assumption, name it);
   Monte Carlo with a seeded numpy generator; report percentiles, not just means.
3. **Optimisation:** keep it simple, a grid or one-dimensional search over the decision value, minimising expected cost;
   no new libraries (numpy/pandas only). Show sensitivity (what-if) on cost ratios and probability error.
4. **Write boundary:** prefer read-only like 1c. If a recommendation table is wanted, make it an opt-in gated,
   guarded write, registered in `OBJECTS` and cleaned up in 99. Ask before adding.
5. **Limits to state plainly:** predictions are uncertain and were validated only offline/live per Module 3 evidence;
   a recommended action is a decision under stated assumptions, not a guarantee; fairness and customer impact of
   turning people away need human judgement.
6. **Non-goals (proposed):** no reinforcement learning, no solver libraries, no live pricing, no automation or
   scheduled jobs (Modules 6 and 8), no new cloud services, no paid model calls.

## Expected deliverables (mirror 1c)
- `notebooks/0Xx_prescriptive_analytics.py` with "Where this sits", Free Edition first, no cloud writes by default.
- Two checked exercises in `lib/a8learn/exercises.py`, same style as 1b/1c.
- `tests/test_prescriptive.py`: SQLite execution, independent Python oracles, seeded simulation checked against a known
  small case (exact binomial enumeration), optimiser checked against brute force.
- Update `docs/index.md`, `START_HERE.md`, 1c "Next" line, `tests/test_stage1.py` notebook set,
  `docs/validation.md`, `docs/issues.md`.
- Run the unit suite and strict docs build **once** at completion. Commit and push only when the user says so.

## Pitfalls seen in 1c
- Writing notebook text through JavaScript `String.raw` left literal `\uXXXX` escapes; check for non-ASCII mangling.
- Ruff line limit is 120 (E501) and applies to notebooks, including Markdown cells.
- Do not assert `Exception` in tests (B017); `A8.expect` raises `AssertionError`.
- Windows PowerShell 5.1: no `&&`; Git warns about LF to CRLF (harmless).
- Avoid printing whole notebooks or full test logs; tail the output.
