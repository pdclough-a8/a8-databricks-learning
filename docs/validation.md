# Stage 1 validation

**Release candidate 0.2.0. Free Edition live acceptance passed, 19 November 2026.**
The earlier pilot's 30-test claim does not certify this replacement.

## Offline evidence

Python 3.12.13 on Windows, dependencies scoped to this repository's ignored `.packages` folder.

| Check | Evidence |
|---|---|
| Final offline suite, including Module 3 file generation | 54 passed; includes Ruff over `lib notebooks tests`. Strict MkDocs build passed |
| `python -m unittest discover -s tests -v` | 37 passed (20 November 2026), including real split/pipeline code, latest-score SQL, lint, partial/repeated cleanup and MLflow ownership helpers |
| `python -m ruff check lib notebooks tests data` | Passed (20 November 2026); also executed by the unit suite |
| `python -m mkdocs build --strict` | Passed after the all-module code-standard rewrite (20 November 2026) |
| Data regeneration | All three generated CSVs byte-identical to supplied data; 60 / 4,204 / 395 rows |
| Independent SQL checks | Exercises 1.1 and 1.2 compared with Python aggregations; exercise 5.1 proved that only the latest prediction per booking is summed |
| Persistence | Save, construct a fresh Course, reload without widgets |
| Lifecycle safety | Wrong confirmation, other owner, absent endpoint, preflight collision and endpoint-only scope |

Offline fakes do not prove Databricks permissions, Delta semantics, registry compatibility or serving.
Notebook source parsing does not execute `%run`, `%pip` or `%sql`.

## Live acceptance

Workspace: **a8-free**, AWS Free Edition, serverless notebook tasks, 19 November 2026.
Each run used a separate, non-Git workspace test folder and the existing `workspace.default` schema.
No original-project files, learner Git folders, schemas or shared endpoints were modified.

Four runs were needed. Runs 1–3 exposed three real defects (issues S09–S11), each fixed and retested.
Run 4 (tag `smoke2`) passed every task:

| Task | Evidence from run 4 |
|---|---|
| 00 setup | Write probe created and dropped; settings saved |
| 01 lakehouse data, separate session | Loaded saved settings (the original pilot failure); 60 / 4,204 / 395 rows; integrity, view, UPDATE and time travel assertions; exercises 1.1, 1.2 correct |
| 02 governance | Row filter and mask attached; only Leeds/Online visible; every email masked; source unchanged; exercises 2.1, 2.2 correct. System lineage/audit queries ran but returned no rows yet (ingestion delay) |
| 03 predictive ML | Train 2,912 / holdout 836 / future 148 bookings. Holdout log loss 0.593 against baseline 0.638, AUC 0.685, accuracy 0.706. Model version 1 with `Champion` alias; reloaded model matched in-memory probabilities |
| Optional serving | Endpoint created, scale-to-zero; online response matched batch probabilities for two bookings |
| Acceptance notebook | Independent CSV-derived counts for policy and predictions, all five exercises, forecast bounds and Delta history passed |
| Cleanup, then cleanup again | First: endpoint, 11 data objects and model deleted, experiment soft-deleted. Second: nothing to delete, no error |
| Rerun on existing objects | Exercised by run 3 for 00–02 (exposed and verified the S10 fix) |

Afterwards, CLI listing confirmed no `a8_smoke*` tables, views, volumes, functions, models or `a8-smoke*`
endpoints remain. Test folders and test settings were deleted. Soft-deleted MLflow experiments remain in
MLflow's normal retention; they hold no endpoint or data objects.

### Explanatory rewrite, 20 November 2026

Three further full runs on a8-free with tag `smoke3`, each setup → data → governance → ML with serving →
acceptance → cleanup → cleanup again. Every task succeeded in all three.

| Run | What it covered |
|---|---|
| 1 | Pushed commit `0ebadd0`: rewritten Module 5, new `claim_experiment`/`claim_model` helpers and folder-lookup fallback |
| 2 | Local rewrite of Modules 0–2 and cleanup; also reused the soft-deleted smoke3 experiment, exercising the restore path |
| 3 | Commit `e4c2aac`: endpoint name passed in the serving config (S15); serving created, queried and deleted |

Afterwards no `a8_smoke3*` tables, views, functions, volumes, models or `a8-smoke3*` endpoints remained;
test folders and test settings were deleted. The vanished-working-folder fallback (S12) was not triggered by
these jobs and remains unverified live. The Git beginner guide is documentation only.

### All-module code standard, 20 November 2026

The first rewrite run, [190892132722849](https://dbc-9293e8d1-d494.cloud.databricks.com/?o=7474653906705547#job/623352491271238/run/190892132722849),
passed setup, data and governance but failed both ML attempts because serverless rejects `.cache()` as
`PERSIST TABLE` (S17). Both cleanup tasks succeeded. The fix removes caching and reads the persisted batch for
later display and serving checks.

The retest, [208516018796520](https://dbc-9293e8d1-d494.cloud.databricks.com/?o=7474653906705547#job/43681650382943/run/208516018796520),
passed setup → data → governance → ML with serving → ML again without serving → acceptance → cleanup → cleanup
again. Acceptance verified two complete appended prediction batches, one latest prediction per future booking,
all five exercises, 12 bounded event forecasts, Delta history and a ready Champion model. The second ML run also
exercised the existing-object and restored-experiment paths.

Afterwards, CLI listing found no `a8_smoke4*` tables/views, volumes, functions or models and no `a8-smoke4*`
endpoints. Both generated test folders and the smoke settings file were deleted. Migration of a prediction table
from the older course schema remains untested live; the rerun used the new schema.

Not yet validated:

| Scenario | Status |
|---|---|
| Rendered notebook UI and UI-route steps | Blocked: browser pane signed into a different Databricks account |
| Paid workspace (Azure) | Not tested: profile needs user OAuth reauthentication |
| A learner editing exercise answers interactively | Not tested; checker verified with supplied solutions and offline wrong-answer cases |
| Ownership conflict with a second real user | Not tested; offline fakes only |

## Module 3: descriptive AI/BI dashboard and Genie

**Supplied, offline checked, not live validated.** No Databricks workspace was contacted for this module.

| Check | Evidence |
|---|---|
| `tests/test_descriptive.py` | 17 passed: the notebook's Python cells execute against the shipped CSVs in SQLite; all 60 `event_metrics` rows match an independent Python aggregation |
| Generated dashboard file | JSON round-trip, learner-view SQL, one dataset, two counters, two bars, one table, city/status/date field bindings, default-no, existing-file preservation and user-folder path checked offline; SDK metadata read mocked |
| Dashboard filter states | All, scheduled, scheduled Leeds and scheduled Leeds in December 2026 reference SQL match independent counts and ticket sums; each state is non-empty |
| Genie SQL | Three example and three held-out reference queries match independent results; example and held-out sets are disjoint |
| Exercises 3.1, 3.2 | Solutions pass; a row count and an unweighted average of averages are rejected |
| Edge cases | Empty event, cancelled-only, unknown attendance, zero capacity and several feedback rows per event give no double-counting and NULL, not zero, where evidence is absent |
| Safety | Default-no gate writes nothing and stops at a named missing-view check; the gate has its own cell; ownership failure stops before CREATE; rerun/resume does not change sources; only one CREATE OR REPLACE VIEW; no personal fields in the view or dashboard dataset |
| Cleanup | `event_metrics` is dropped before its source tables; generated files, dashboards and Genie spaces are explicitly out of scope of the cleanup notebook |

SQLite checks relational logic only. Not validated: Spark SQL/Unity Catalog execution of the view, the
rendered dashboard, live filter behaviour, notebook-written file recognition as FILE versus DASHBOARD, UI import,
Genie availability on Free Edition, Genie answers, benchmarks, UI labels and manual UI cleanup.
The widget-display fix is covered by offline cell-order checks but has not been re-observed live.
`live_smoke.py` does not run Module 3, and its acceptance notebook now checks only the
original five exercises, so it makes no claim about this module.

The overview now maps analytics levels to modules and labels diagnostic/prescriptive content as planned.
Notebook headers identify their place in that map. This framing is documentation, not evidence of new capability.
Dashboard API deployment and programmatic Genie creation are deferred to Module 12; Module 11 is conversation-only.

No GenAI, RAG, MCP or app validation is claimed: these are Stage 2 modules, not supplied in this release.

## Reproduce as a maintainer

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m mkdocs build --strict
```

`tests/live_smoke.py --approve-cloud-writes` is **not an offline test**. It uploads and runs notebooks
against the explicitly named `a8-free` OAuth profile, creates exact `a8_smoke_*` objects and opts into
serving. Only run after approval and after checking that `smoke` does not belong to another course run.
It schedules full course cleanup and a second idempotency cleanup even when teaching tasks fail.
If cleanup itself is blocked, inspect the failure and run `99_pause_and_cleanup` with profile
`stage1_smoke`, matching confirmation and cleanup action afterwards. After successful validation,
remove only the generated test folder and test settings. It never pushes Git changes.

## Boundaries

Timing estimates have not been tested with novice learners. One owner identity does not validate
multi-user separation. The demo mask is not anonymisation. This synthetic turnout model is not a
production forecasting product. Feature availability, quotas, retained storage and costs differ by workspace.
Dependency versions are direct pins, not a fully locked runtime image.

## Module 9: Agents

**Supplied, offline checked, not live validated.**

| Check | Evidence |
|---|---|
| `tests/test_agents.py` | The notebook runs against SQLite copies of the shipped events, bookings and documents, with `ai_query` replaced by a scripted stand-in |
| Gates | The default run makes no model request and executes no write; the one model step is a default-no switch with a fixed 12-request budget |
| Guardrails | Unknown tools, wrong inputs, extra inputs and failing tools become error messages; a decider that never finishes is stopped at four tool calls |
| Model replies | Treated as untrusted text: only valid JSON of the expected shape is acted on; errors and chatter stop the task without a crash |
| Tool input | Travels as a SQL parameter; a hostile string returns no rows and never appears in the statement |
| Exercises 9.1, 9.2 | The solutions equal independent Python results; blank and naive answers fail |

Not validated offline: whether a real model follows the JSON format, picks the right tool or refuses the weather
question; quota; notebook rendering.

## Module 8c: Vector Search

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026** (run `tests/live_smoke_stage2.py`).

| Check | Evidence |
|---|---|
| `tests/test_vector_search.py` | The notebook runs against an in-memory stand-in for the Databricks SDK's Vector Search endpoints and indexes |
| Gates | The default run makes no create, query, chat or delete call; each billable step is its own default-no switch |
| Index definition | Built from the SDK's typed classes: your chunk table as source, `chunk_id` as key, `content` embedded with the saved embedding endpoint, triggered sync, columns listed |
| Cleanup | The index is deleted before the endpoint; resources not created by you, or an endpoint hosting other indexes, are refused; `99_pause_and_cleanup` uses the same code |
| Exercise 8c.1 | A PySpark-style result equals the SQL solution; blank and wrong answers fail |

Live result (Free Edition, serverless): the endpoint was online at once and the index became ready; all 32 chunks were indexed. On the eight evaluation questions the index scored hit@1 1.00 and hit@3 1.00 against 0.50 and 0.88 for word overlap. The grounded answer cited the right document and the weather question was refused. The in-notebook deletion and `99_pause_and_cleanup` removed the index and endpoint; no endpoint, table or volume was left.

Not validated: paid-workspace behaviour and any quota other than that of this one run.

## Module 8b: RAG

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026.** Live result: nine documents copied to the volume, 32 chunks, the chunk table created, 41 texts embedded (1,024 numbers each), embedding retrieval hit@1 1.00 and hit@3 1.00 against 0.50 and 0.88 for word overlap, one cited answer and one refusal.

| Check | Evidence |
|---|---|
| `tests/test_rag.py` | The notebook's Python cells run against the shipped documents and synthetic tables, with stand-ins for `ai_query` |
| Gates | The default run makes zero model statements; an approved embedding run sends every chunk and question once, an approved chat run sends exactly two prompts, text always as parameters |
| Chunks | Nine documents give the expected chunks, each within the length limit with unique ids; the chunk table has one row per chunk, change data feed on and ownership labels set |
| Retrieval | Word-overlap hit at k is computed offline; the evaluation set and its expected documents are checked against the documents |
| Exercises 8b.1, 8b.2 | Solutions equal independent Python; blank and naive answers fail |

Not validated: `ai_query` against an embedding endpoint and a chat endpoint on Free or paid workspaces, `failOnError`
and `modelParameters` behaviour, endpoint names, answer and citation quality, refusal behaviour, creating a directory in
a volume, and notebook rendering. The documents are short and tidy, so retrieval looks easier than on real documents.

## Module 8a: embeddings

**Supplied and offline checked. The SQL embedding route was live validated on `a8-free` on 24 November 2026** (1,024-number vectors). **The Python (SDK) route timed out after five minutes in that run** and now falls back to the SQL route with a message; it is not validated.

| Check | Evidence |
|---|---|
| `tests/test_embeddings.py` | The notebook's Python cells run against synthetic `feedback` and `events` tables with a deterministic stand-in for `ai_query` |
| Gate | The default run makes zero `ai_query` statements and no writes; an approved run sends exactly 30 texts in one query, as parameters |
| Vectors by hand | Bag-of-words and cosine results match the lesson text: the top match for the stream complaint is the stream praise, and the audio complaint scores 0 |
| Exercises 8a.1, 8a.2 | Solutions equal independent Python; blank and naive answers fail |

Not validated: whether `ai_query` accepts an embedding endpoint and returns `ARRAY<FLOAT>` on Free or paid workspaces,
endpoint names and quota, the quality of real embeddings on these comments, and notebook rendering. The comments repeat
27 templates, so results look cleaner than real feedback. The lesson states the expected ranking only as a prediction.

## Module 7: GenAI

**Supplied, offline checked, not live validated.** No workspace, model or AI Function was contacted.

| Check | Evidence |
|---|---|
| `tests/test_genai.py` | The notebook's Python cells run against a synthetic `feedback` table with a deterministic stand-in for AI Functions |
| Gates | Default run makes zero AI statements and no writes; approvals are consumed after one use; a missing note, or a missing `databricks-` endpoint for `ai_query`, is refused before any request |
| Input | Five-comment, ordered, parameterised sample; comment text never appears in SQL text |
| Exercises 7.1, 7.2 | Solutions equal independent Python; naive (NULL-dropping) and blank answers fail |

Not validated: availability, pricing or quota on Free Edition or paid workspaces, the Playground UI, the `ai_classify` 2.1
VARIANT shape, parameter markers inside AI Function arguments, endpoint names, output quality, and notebook rendering.
Synthetic comments repeat a few templates, so results look cleaner than real feedback.

## Module 6: prescriptive analytics

**Supplied, offline checked, not live validated.** No Databricks workspace was contacted for this module.

| Check | Evidence |
|---|---|
| `tests/test_prescriptive.py` | 14 tests: the notebook's Python cells execute against a synthetic `attendance_predictions` table (two model versions per booking) and an `event_forecast` table built by independent Python, not by Module 5's model or SQL |
| Overbooking | The simulated best ticket limit is within 1% of the brute-force minimum of the exact binomial cost, and within 8 tickets of its argmin (the cost curve is flat near the minimum); limit rises with the cost of turning people away and falls as show probability rises |
| Turnout simulation | Seeded and repeatable; matches exact enumeration of all 16 outcomes of a four-booking case within 0.01 per outcome |
| Catering | The chosen order is within 1% of the exact-distribution minimum (dynamic programming) and within 2 meals of its argmin; exact mean and variance match sum(t x p) and sum(t^2 x p x (1 - p)) |
| Exercises 6.1, 6.2 | Solutions equal independent Python results for every scheduled event; rounding instead of truncating, and ignoring the latest-score rule, are rejected, as are blank answers |
| Safety | No CREATE/DROP/INSERT/UPDATE/DELETE, no gate, guard, file write, AI call or MLflow; imports only math, numpy and pandas; missing prerequisites stop before any query; completed, unknown and injection-style event ids are rejected; the event id is a query parameter |
| Navigation and branding | Index, START_HERE and the Module 3/4 next-step lines point to 6; the supplied logo file is a PNG referenced by mkdocs, README, START_HERE and the overview |

Illustration only, from the synthetic test predictions (not Module 5's real model): for E150 the simulated cheapest limit was
201 tickets against a simple rule of 208, and the cheapest order was 44 meals for 59 tickets and 42.6 expected attendees.
Real learner results will differ with their own model version and costs.

Not validated: Spark SQL execution (named `:event_id` parameters, `row_number()` with `NULLS LAST`, `toPandas()` on
serverless), the notebook rendering in Databricks, and the logo and white header rendering in the built site (checked only that
the strict build passes, not by eye in a browser). Probabilities from Module 5 are treated as calibrated; independence between
bookings is an assumption; costs are assumed teaching parameters with no payment ledger behind them.

## Module 4: diagnostic analytics

**Readability pilot (23 November 2026), offline only:** one setup cell, an "Under the hood" helper table, three optional
`<details>` background blocks (event terms, mix versus rate, p-value) and three computed "Reading" cells that state the
real values with their limits. `tests/test_diagnostic.py` checks the single setup cell and the reading variables.
Not validated: Databricks rendering of `<details>` in Markdown cells, and whether learners find it clearer (no learner testing).

**Supplied, offline checked, not live validated.** No Databricks workspace was contacted for this module.

| Check | Evidence |
|---|---|
| `tests/test_diagnostic.py` | 11 tests: the notebook's Python cells execute against an `event_metrics` table built from the shipped CSVs by independent Python, not by Module 3's SQL |
| Drill-downs | City, topic, format and month results match an independent aggregation (events, tickets, attendance %, responses, rating) |
| Mix versus rate | Attendance and rating splits match an independent two-segment calculation; effects add to the overall gap. On the shipped data: attendance gap -17.7 points = mix +1.1 and rate -18.9; rating gap -0.11 = mix -0.01 and rate -0.10 |
| Permutation test | Observed gap equals the SQL gap; seeded, repeatable; p agrees with a separate stdlib shuffle (different RNG, 20,000 runs) within 0.01; a six-event case matches exact enumeration of all 20 labelings within 0.02. Shipped data: p = 0.0003 with 10,000 shuffles, the floor for that count |
| Exercises 4.1, 4.2 | Solutions pass; unweighted averages of event-level rates/ratings and blank answers are rejected |
| Safety | No CREATE/DROP/INSERT/UPDATE/DELETE, no gate, no file write; imports only numpy; missing `event_metrics` stops before any query; unknown drill-down dimensions are rejected |

SQLite checks relational logic only. Not validated: Spark SQL execution (notably `substr` on a DATE column for the month cut),
`toPandas()` on serverless, the dashboard filter walk-through, Genie availability and answers (checkpoint G2), UI labels.
The test explains chance only for one segment pair; it does not adjust for confounders, and the data cannot separate
city from format for online events.
