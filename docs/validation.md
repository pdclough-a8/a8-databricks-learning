# Validation evidence

## Design review changes, 24 November 2026

**Offline checked only; no cloud operations or model requests were made.** Added the
[design rationale](design-rationale.md), decision tasks 13.3 (SQL), 14.2 and 15.2 (Python rules checked by
`A8.check_rule`), and self-check criteria with a neutral, explicitly unmarked card for every reflection.

Tests cover: the 13.3 solution against an independent Python calculation of the dropped batch rows and their rules,
and a single-rule answer failing; every rule solution passing all cases; unfinished (`...`), missing,
non-function and error-raising answers; feedback naming the case for typical wrong rules (the lesson's single
tolerance, ignoring the gate result, returning a dict); instructor mode; and reflection criteria and styling.
Not yet observed: 13.3 against a real bronze table, and how learners respond to the new tasks and criteria.

Final checks on Python **3.12.13**: **244 tests passed**, including Ruff, in **16.802 seconds**;
`python -m mkdocs build --strict` passed.

## Audit remediation, 24 November 2026

**Current changes are offline checked only; Databricks retesting is for the learner.** The earlier live runs below
are historical evidence and do not certify the revised code. No cloud operations or model requests were made in
this remediation pass.

Corrections cover endpoint-only cleanup scope, retained-batch reruns/rebuilds, explicit gold-versus-historical
source selection in Modules 11/14/15, a real snapshot reread, malformed tool replies, consistent numerical exercise
comparison, whole signed seat-count scoring, SQL statement polling/cancellation and question-keyed RAG citations.
Vector Search now retrieves each evaluation question once at k=3 and reuses it for hit@1 and hit@3 (eight queries).
Guidance now distinguishes alias loads from pinned endpoint deployments, runnable repository copies from saved
notebook copies, and delivered modules from planned MCP work.

Regression evidence includes the same in-memory tables passed from Module 13 to 14 and 15. With three batches,
the expected counts become **11 and 22**, rather than the historical **27 and 44**; the old endpoint snapshot is
blocked and the fresh candidate passes. App tests cover PENDING -> RUNNING -> SUCCEEDED and timeout cancellation,
not a rendered Streamlit session. SQL/SDK/MLflow stand-ins still do not prove platform behaviour.

Final checks on Python **3.12.13**: **240 tests passed**, including Ruff, in **18.991 seconds**;
`python -m mkdocs build --strict` passed. Generated logs are kept locally in ignored `.local-validation/`.

### Learner Databricks retest

1. Open the updated full repository and reset the notebook environment so imports use the changed library.
   Continue with your existing tag/settings; do not reset Module 1 unless you intend to reset its source fixtures.
2. In Module 13, run with the existing batch folder. Repeat the completed lesson, then its approved cleanup/rebuild:
   no files should be overwritten and checks should accept every retained batch. On the final run, keep its gold
   tables (`delete_pipeline_objects = no`) for the next lessons.
3. In Module 11, check setup names `seats_live`, approve creation/reuse, grants and deployment, then open the actual
   page. Confirm the table/threshold and identity panel, including warehouse startup. The deployment step refreshes
   the course app's source/settings; deletion revokes access to both possible course data sources.
4. In Module 14, check setup names `seats_live`, run the evaluation and optionally test an existing Module 12 endpoint
   that still carries the pre-pipeline snapshot. It should be blocked on the seat figures. The refreshed candidate
   really rereads the selected tables. Module 15 should also use gold for its facts, gate and exercise.
5. Retest Module 9's optional model routes and Modules 8b/8c's displayed citations only if you approve their model
   requests. The model-free guardrail/citation regression tests do not establish actual model quality.
6. Preview Module 99. `endpoint_only` must leave the app, job, pipeline and their data in place; it is not an
   all-compute-stop switch. Remove apps/jobs/pipelines in their own lessons or choose `all_course_objects`, checking
   its expanded preview first. Full cleanup remains destructive and requires your exact learner tag.

Modules 6/7 and the complete Module 15 notebook still need their first live notebook validation. Dashboard/Genie UI
behaviour, rendered app results and paid-workspace behaviour remain outside this offline evidence.

## Historical validation ledger

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

**Notebook live run (24 November 2026, `a8-free`, serverless, solution answers):** it ran end to end, and the pandas route agreed with the SQL view on every metric. **Dashboard import and Genie remain not live validated.** Earlier text below describes the offline checks.

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

At that earlier stage the overview mapped analytics levels to modules and labelled diagnostic/prescriptive content as planned.
Notebook headers identify their place in that map. This framing is documentation, not evidence of new capability.
Dashboard API deployment and programmatic Genie creation were deferred. Neither is supplied by the current Module 12.

At that release point no GenAI, RAG, MCP or app validation was claimed. Later evidence is recorded by module below;
only MCP remains unsupplied.

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

## Module 13: Pipelines and jobs

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026.** Live result: the `${...}` pipeline
settings worked inside table names; update 1 produced bronze 43, silver 40 and gold 60 rows with each rule dropping
one row; gold matched the independent calculation after batch 1 and after batch 2; update 2 read only the new file
(bronze 86, two source files); a job with a paused schedule ran the pipeline once with a third batch and succeeded; the
notebook then deleted the job, the pipeline and the three tables. The event-log quality counts read correctly over REST.
The static view showed seats left too high for moved events, and one small event came out oversold (-1), which the
notebook now points out. `system.lakeflow.job_run_timeline` did not list the run within the notebook's few minutes, so
the notebook says it can lag.

| Check | Evidence |
|---|---|
| `tests/test_pipelines.py` | The notebook runs against recording stand-ins for the SDK and Spark, with a small Python model of the pipeline's three layers |
| Batches | Deterministic: 43 rows each (40 valid, 3 bad); the bad rows break the ticket, status and id rules |
| Gates | The default run lands batch 1 in your volume and nothing else; create, run, job and delete are separate default-no switches |
| Pipeline | Serverless, triggered, development mode, created from the repo SQL file with your table names as settings; reused only if it is yours |
| Independent check | Gold's seats left equal Module 1's seats left minus the valid confirmed tickets counted in Python from the batch rows |
| Job | Created with a paused schedule and course tags; run once; reused only if it is yours |
| Cleanup | The job, then the pipeline, then the three tables (deleting a pipeline leaves them behind) after exact-name, creator and marker checks; `99_pause_and_cleanup` uses the same code |
| Exercises 13.1, 13.2 | The solutions equal independent Python results; blank and naive answers fail |

Not live validated: paid-workspace behaviour, and the system-table read-out of the run (it lagged).

## Module 11: Interactive app

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026 (serverless notebook run).** Live
result: the app was created with the warehouse resource and course marker; the service principal received the three
grants and `SHOW GRANTS` listed `SELECT` on the view; deploying from `/Workspace` plus the folder succeeded (without
that prefix the deploy is rejected), the app reached RUNNING, a signed-in request returned 200, the app ran as a
different identity from the learner, exercise 11.1 passed, and the notebook deleted the app, grants and folder; the
workspace app list was empty afterwards and the scoped cleanup found nothing left. A separate probe showed the viewer's
email arrives in `X-Forwarded-Email`.

**Not verified:** what the page itself shows. The check only proves the Streamlit shell is served (HTTP 200), so the
warehouse query inside the app, the `valueFrom` warehouse id and the identity panel were not seen rendered; open the
app once in a browser to confirm. Revokes were run but not read back.

| Check | Evidence |
|---|---|
| `tests/test_app.py` | The notebook runs against recording stand-ins for the SDK and Spark; audit regressions also execute the app query function with fake statement states, without running Streamlit |
| Gates | The default run calls nothing; create, grant, deploy and delete are separate default-no switches |
| App | Created with your warehouse as a `CAN_USE` resource and a course marker in its description; reused only if it is yours |
| Grants | `USE CATALOG`, `USE SCHEMA` and `SELECT` on the selected aggregate view/table; deletion revokes access to both possible course sources |
| Deploy | The source path is `/Workspace` plus the folder |
| Cleanup | Grants revoked, then the app deleted after exact-name, creator and marker checks, then the folder; `99_pause_and_cleanup` uses the same code |
| App source | Read-only, no credentials in the source, takes its warehouse and view from the environment |
| Exercise 11.1 | The solution equals an independent result; blank and naive answers fail |

Not live validated: the rendered page (see above) and paid-workspace behaviour.

## Module 12: Deploy and govern

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026.** Live result: the packaged agent
scored 4 of 5 grounded; logging a model from a code file worked once MLflow 3.6.0 was pinned (the serverless default
rejected `log_model(name=...)`); the released `Champion` model answered exactly as the tested code; the scale-to-zero
endpoint became ready, answered identically, showed you and `admins` with `CAN_MANAGE`, and was deleted by the
notebook; cleanup removed the model. The governance read-outs for aliases and grants failed in that run and were
changed to REST calls, which are checked offline only. A write probe also showed an app can be created and deleted on Free.

| Check | Evidence |
|---|---|
| `tests/test_deploy.py` | The notebook runs against recording stand-ins for MLflow, the SDK client and Spark; the agent code is real |
| Packaged agent | `agent_core.py` matches the Module 9 baseline (four of five grounded) and keeps the allow-list, input checks and step cap; the wrapper loads a snapshot and returns one row per question |
| Gates | The default run makes no MLflow write and no SDK call; register, deploy and delete are separate default-no switches |
| Registration | One run with course tags, the code, the snapshot and an input example; a new version each time; the `Champion` alias; the released model must answer as the tested code did |
| Serving | The endpoint is pinned to the registered version, tagged, scale to zero, never updated if it exists, and refused if it is not yours; its answers must equal the local ones |
| Cleanup | The agent endpoint is deleted only for its creator with matching tags; the agent model, its aliases and versions are removed by `99_pause_and_cleanup` after the same ownership check |
| Exercises 12.1, 12.2 | The solutions equal independent Python results; blank and naive answers fail |

Not live validated: the revised alias and grants read-outs, and paid-workspace behaviour.

## Module 9: Agents

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026.** Live result: the tools, guardrails and loop ran as designed. The rule-based agent scored tool choice 5/5 and grounded 4/5 (it ranks the wrong section first for "take over my seat"). The JSON model decider scored 5/5 and 5/5 in 9 of 12 requests, and refused the weather question. **Native tool-calling works on Free** with `databricks-meta-llama-3-3-70b-instruct`: tool choice 5/5, grounded 4/5 in 9 of 12 requests; the miss is the same retrieval miss, not a tool-calling failure. Nothing was created.

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
| Gates | With no existing index, the default run makes no create, query, chat or delete call; a retained ready index is queried by the demonstration/evaluation cells. Create, chat and delete are default-no |
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

Remaining limits: paid-workspace behaviour, general answer/citation quality beyond the recorded examples, and the
revised citation-row association (offline only). The documents are short and tidy, so retrieval looks easier than
on real documents.

## Module 8a: embeddings

**Supplied and offline checked. The SQL embedding route was live validated on `a8-free` on 24 November 2026** (1,024-number vectors). **The Python (SDK) route timed out after five minutes in that run** and now falls back to the SQL route with a message; it is not validated.

| Check | Evidence |
|---|---|
| `tests/test_embeddings.py` | The notebook's Python cells run against synthetic `feedback` and `events` tables with a deterministic stand-in for `ai_query` |
| Gate | The default run makes zero `ai_query` statements and no writes; an approved run sends exactly 30 texts in one query, as parameters |
| Vectors by hand | Bag-of-words and cosine results match the lesson text: the top match for the stream complaint is the stream praise, and the audio complaint scores 0 |
| Exercises 8a.1, 8a.2 | Solutions equal independent Python; blank and naive answers fail |

Remaining limits: the Python SDK route, paid-workspace endpoint names/quota, general embedding quality and notebook
rendering. The recorded Free SQL run returned vectors successfully. The comments repeat
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

**Notebook live run (24 November 2026, `a8-free`, serverless, solution answers):** it ran end to end after a Decimal fix, including the pandas drill-down check and the permutation test. **Genie remains not live validated.**

**Readability pilot (23 November 2026), offline only:** one setup cell, an "Under the hood" helper table, three optional
`<details>` background blocks (event terms, mix versus rate, p-value) and three computed "Reading" cells that state the
real values with their limits. `tests/test_diagnostic.py` checks the single setup cell and the reading variables.
Not validated: Databricks rendering of `<details>` in Markdown cells, and whether learners find it clearer (no learner testing).

**Earlier offline-only evidence:** the following Module 4 checks predate the live run recorded above.

| Check | Evidence |
|---|---|
| `tests/test_diagnostic.py` | 11 tests: the notebook's Python cells execute against an `event_metrics` table built from the shipped CSVs by independent Python, not by Module 3's SQL |
| Drill-downs | City, topic, format and month results match an independent aggregation (events, tickets, attendance %, responses, rating) |
| Mix versus rate | Attendance and rating splits match an independent two-segment calculation; effects add to the overall gap. On the shipped data: attendance gap -17.7 points = mix +1.1 and rate -18.9; rating gap -0.11 = mix -0.01 and rate -0.10 |
| Permutation test | Observed gap equals the SQL gap; seeded, repeatable; p agrees with a separate stdlib shuffle (different RNG, 20,000 runs) within 0.01; a six-event case matches exact enumeration of all 20 labelings within 0.02. Shipped data: p = 0.0003 with 10,000 shuffles; the corrected estimator's minimum possible value is 1/10,001, about 0.0001 |
| Exercises 4.1, 4.2 | Solutions pass; unweighted averages of event-level rates/ratings and blank answers are rejected |
| Safety | No CREATE/DROP/INSERT/UPDATE/DELETE, no gate, no file write; imports only numpy; missing `event_metrics` stops before any query; unknown drill-down dimensions are rejected |

SQLite checks relational logic only. The later live Module 4 run exercised Spark SQL and serverless pandas.
Remaining gaps: the dashboard filter walk-through, Genie availability/answers (checkpoint G2), and UI labels.
The test explains chance only for one segment pair; it does not adjust for confounders, and the data cannot separate
city from format for online events.

## Module 14: Evaluate and monitor

**Supplied and offline checked. Live validated on `a8-free` on 24 November 2026, except the endpoint test.** Live
result (second run; the first failed at the trace cell, because MLflow 3.6 returns the `trace` column of
`search_traces` as text, and the notebook now reads spans with `mlflow.get_trace`): the baseline was grounded on 4 of 5
tasks and finished all five; the stale candidate was blocked on `grounded` while still finishing every task; the
refreshed candidate was released; fifteen traces were found, one showing a `support_agent` span with a `search_docs`
tool span; the summary reported no failures; the judge cell ran and its in-notebook check passed; cleanup deleted the
evaluation experiment and left nothing behind. The judge's printed mark and the run means were cut from the exported
output, so their values are not recorded here. Earlier, a throwaway probe on `a8-free` (one serverless run, MLflow
3.6.0, everything deleted afterwards) had proved the platform calls it relies on: `mlflow.genai.evaluate()` with two custom `@scorer` functions on two rows returned the expected means; `@mlflow.trace`
produced traces that `mlflow.search_traces` returned; and a `Guidelines` judge with
`model="databricks:/databricks-meta-llama-3-3-70b-instruct"` returned a mark (one paid model request). Not probed:
tagging a run after `evaluate()` has finished, `search_traces` on an experiment with several runs, the nested tool spans
under `@mlflow.trace`, calling the Module 12 endpoint as the predict function, the `Correctness` and `Safety` judges, and
Unity Catalog evaluation datasets (the module uses none). The probe's untested items marked above, except the endpoint
and the other judges, were exercised by the live run.

| Check | Evidence |
|---|---|
| `tests/test_evaluation.py` | The notebook runs against a stand-in MLflow that really calls the predict function and the scorers, so the marks and the gate decisions are the notebook's own; it does not show how MLflow behaves |
| Rules | Right tool, grounded and finished are plain functions; the seat rule needs the whole number followed by "seats left", so `15 seats left` does not satisfy a fact of `5` |
| Gate | Blocks any scorer that falls below the baseline (a tolerance can be set), requires `finished` to be 1.0, and treats a missing metric as a failure |
| Candidate | A copy of the snapshot with every seat count out by seven: it still finishes every task and is blocked on `grounded` alone |
| Gates (switches) | The default run writes nothing; run_evaluation, run_judge and evaluate_endpoint are separate default-no switches; the endpoint test never creates or deletes an endpoint |
| Names | Evaluation runs go to their own experiment (`a8learn_<tag>_agent_eval`), claimed with the same ownership check as Module 12's, and carry the course tags |
| Cleanup | `99_pause_and_cleanup` deletes the evaluation experiment after a course-tag check, before any other delete; a foreign experiment stops the cleanup |
| Exercise 14.1 | The solution equals an independent result computed from the CSV files; blank and naive answers fail |

Not live validated: the endpoint test (no endpoint existed in the run, so it was skipped), the `Correctness` and
`Safety` judges, paid-workspace behaviour, and production trace ingestion into Unity Catalog and scheduled monitors,
which the notebook describes and does not run.

## Module 15: Release gate and rollback

**Supplied and offline checked. The traffic split was probed live on `a8-free` on 24 November 2026; the notebook itself
has not been run live.** The notebook, `lib/a8learn/release.py` and
`tests/test_release.py` exist, and the harness task `release` in `tests/live_smoke_stage2.py` is ready (canary off), but
no live run has happened. The harness needs the `deploy` task before it, because the lesson releases the Champion that
Module 12 registers (for example `--only setup,data,rag,deploy,release`).

| Check | Evidence |
|---|---|
| `tests/test_release.py` | The notebook runs against a stand-in registry that keeps versions, tags and the alias, and a stand-in serving API that keeps the endpoint's served entities and routes; evaluation really runs the agent and the scorers. It does not show how MLflow 3.6 or Model Serving behave |
| Release order | The fresh candidate is released first and the stale one is gated against the new Champion. A test builds a stale Champion and shows the stale candidate would tie with it and pass if gated against it, which is why the order matters |
| Alias | `Champion` moves only for a candidate that passed; the blocked version never holds it; every version gets its gate result, reasons, evaluation run id and the version compared with, and the released one a `replaces` tag |
| Rollback | Moves the alias to `replaces`, tags the withdrawn version, refuses when no `replaces` tag exists, and the notebook checks the restored Champion gives the five answers recorded before the release |
| Gates (switches) | The default run writes nothing; `log_candidates`, `release_candidate`, `roll_back` and `canary_endpoint` are separate default-no switches; the notebook never creates or deletes an endpoint, model or experiment |
| Canary | Splits 90/10, sends 20 requests and restores in a `finally` block (tested with a failing request); skips when the endpoint is absent, not yours, or does not serve one version of the agent model |
| Cleanup | No new object type: the model with all its versions and aliases is removed by the existing cleanup. The evaluation experiment is deleted only when data objects are also removed (`tables=True`), as for Module 14 |
| Exercise 15.1 | The solution equals an independent result computed from the CSV files; blank and naive answers fail |

Canary probe (24 November 2026, `a8-free`, approved, throwaway model with two versions and one endpoint, all deleted
afterwards; nothing was left in the workspace). Confirmed: Free Edition accepts two served versions with a 90/10
traffic split on one endpoint through `PUT /api/2.0/serving-endpoints/<name>/config`. The route field is
`served_model_name` (replies also carry `served_entity_name`), and the state fields are `config_update` and `ready`, as
the notebook reads them. The API names a served entity `<model>-<version>`, which is why the notebook reads the name
from the endpoint and does not assume one. Timing: creating the endpoint took about 6 minutes, the split update about
6 minutes, the restore 15 seconds. Twenty requests to the split endpoint returned both versions (19 and 1) when the
two versions gave different answers, so a split is observable; in the lesson both versions give identical answers, so
it is shown by the routes only. The notebook's own canary cells have not been run live.

Not live validated: the notebook itself (versions, evaluation of loaded models, the alias move, the rollback and its
answer check, the canary cells), paid-workspace behaviour, and these calls that no probe touched:
`get_model_version_by_alias` and version tags in Unity Catalog, loading `models:/<name>/<n>`, and
`mlflow.genai.evaluate` on a loaded model. Loaded models do not produce tool spans, so the lesson does not assert them.
A gate only compares: if the Champion's own figures are out of date, an equally stale candidate would pass, which the
notebook says.
