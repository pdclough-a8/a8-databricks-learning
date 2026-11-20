# Stage 1 validation

**Release candidate 0.2.0. Free Edition live acceptance passed, 19 November 2026.**
The earlier pilot's 30-test claim does not certify this replacement.

## Offline evidence

Python 3.12.13 on Windows, dependencies scoped to this repository's ignored `.packages` folder.

| Check | Evidence |
|---|---|
| Final offline suite, including Module 1b file generation | 54 passed; includes Ruff over `lib notebooks tests`. Strict MkDocs build passed |
| `python -m unittest discover -s tests -v` | 37 passed (20 November 2026), including real split/pipeline code, latest-score SQL, lint, partial/repeated cleanup and MLflow ownership helpers |
| `python -m ruff check lib notebooks tests data` | Passed (20 November 2026); also executed by the unit suite |
| `python -m mkdocs build --strict` | Passed after the all-module code-standard rewrite (20 November 2026) |
| Data regeneration | All three generated CSVs byte-identical to supplied data; 60 / 4,204 / 395 rows |
| Independent SQL checks | Exercises 1.1 and 1.2 compared with Python aggregations; exercise 3.1 proved that only the latest prediction per booking is summed |
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
| 1 | Pushed commit `0ebadd0`: rewritten Module 3, new `claim_experiment`/`claim_model` helpers and folder-lookup fallback |
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
| Azure paid (`users.pclough`) | Not tested: profile needs user OAuth reauthentication |
| A learner editing exercise answers interactively | Not tested; checker verified with supplied solutions and offline wrong-answer cases |
| Ownership conflict with a second real user | Not tested; offline fakes only |

## Module 1b: descriptive AI/BI dashboard and Genie

**Supplied, offline checked, not live validated.** No Databricks workspace was contacted for this module.

| Check | Evidence |
|---|---|
| `tests/test_descriptive.py` | 17 passed: the notebook's Python cells execute against the shipped CSVs in SQLite; all 60 `event_metrics` rows match an independent Python aggregation |
| Generated dashboard file | JSON round-trip, learner-view SQL, one dataset, two counters, two bars, one table, city/status/date field bindings, default-no, existing-file preservation and user-folder path checked offline; SDK metadata read mocked |
| Dashboard filter states | All, scheduled, scheduled Leeds and scheduled Leeds in December 2026 reference SQL match independent counts and ticket sums; each state is non-empty |
| Genie SQL | Three example and three held-out reference queries match independent results; example and held-out sets are disjoint |
| Exercises 1b.1, 1b.2 | Solutions pass; a row count and an unweighted average of averages are rejected |
| Edge cases | Empty event, cancelled-only, unknown attendance, zero capacity and several feedback rows per event give no double-counting and NULL, not zero, where evidence is absent |
| Safety | Default-no gate writes nothing and stops at a named missing-view check; the gate has its own cell; ownership failure stops before CREATE; rerun/resume does not change sources; only one CREATE OR REPLACE VIEW; no personal fields in the view or dashboard dataset |
| Cleanup | `event_metrics` is dropped before its source tables; generated files, dashboards and Genie spaces are explicitly out of scope of the cleanup notebook |

SQLite checks relational logic only. Not validated: Spark SQL/Unity Catalog execution of the view, the
rendered dashboard, live filter behaviour, notebook-written file recognition as FILE versus DASHBOARD, UI import,
Genie availability on Free Edition, Genie answers, benchmarks, UI labels and manual UI cleanup.
The widget-display fix is covered by offline cell-order checks but has not been re-observed live.
`live_smoke.py` does not run Module 1b, and its acceptance notebook now checks only the
original five exercises, so it makes no claim about this module.

The overview now maps analytics levels to modules and labels diagnostic/prescriptive content as planned.
Notebook headers identify their place in that map. This framing is documentation, not evidence of new capability.
Dashboard API deployment and programmatic Genie creation are deferred to Module 8; Module 7 is conversation-only.

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

## Module 1c: diagnostic analytics

**Supplied, offline checked, not live validated.** No Databricks workspace was contacted for this module.

| Check | Evidence |
|---|---|
| `tests/test_diagnostic.py` | 11 tests: the notebook's Python cells execute against an `event_metrics` table built from the shipped CSVs by independent Python, not by 01b's SQL |
| Drill-downs | City, topic, format and month results match an independent aggregation (events, tickets, attendance %, responses, rating) |
| Mix versus rate | Attendance and rating splits match an independent two-segment calculation; effects add to the overall gap. On the shipped data: attendance gap -17.7 points = mix +1.1 and rate -18.9; rating gap -0.11 = mix -0.01 and rate -0.10 |
| Permutation test | Observed gap equals the SQL gap; seeded, repeatable; p agrees with a separate stdlib shuffle (different RNG, 20,000 runs) within 0.01; a six-event case matches exact enumeration of all 20 labelings within 0.02. Shipped data: p = 0.0003 with 10,000 shuffles, the floor for that count |
| Exercises 1c.1, 1c.2 | Solutions pass; unweighted averages of event-level rates/ratings and blank answers are rejected |
| Safety | No CREATE/DROP/INSERT/UPDATE/DELETE, no gate, no file write; imports only numpy; missing `event_metrics` stops before any query; unknown drill-down dimensions are rejected |

SQLite checks relational logic only. Not validated: Spark SQL execution (notably `substr` on a DATE column for the month cut),
`toPandas()` on serverless, the dashboard filter walk-through, Genie availability and answers (checkpoint G2), UI labels.
The test explains chance only for one segment pair; it does not adjust for confounders, and the data cannot separate
city from format for online events.
