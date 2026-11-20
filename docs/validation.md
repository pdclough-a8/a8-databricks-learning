# Stage 1 validation

**Release candidate 0.2.0. Free Edition live acceptance passed, 19 November 2026.**
The earlier pilot's 30-test claim does not certify this replacement.

## Offline evidence

Python 3.12.13 on Windows, dependencies scoped to this repository's ignored `.packages` folder.

| Check | Evidence |
|---|---|
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
