# Issues and decisions

Stage 1 replaces the pilot. Historical pilot evidence is not carried over as acceptance evidence.

| ID | Status | Issue or decision |
|---|---|---|
| S01 | Fixed, live verified | Notebook widget values did not persist across `%run`; use saved configuration |
| S02 | Implemented | Lesson material belongs inside notebooks; old guides and fixture-only app removed |
| S03 | Open | Official logo/font/colour assets not supplied; provisional text branding retained |
| S04 | Blocked for Azure | a8-paid profile needs user OAuth reauthentication |
| S05 | UI validation blocked | Embedded browser is not signed into Databricks |
| S06 | Intentional | Solo learner policy affects everyone; no invented group or privilege escalation |
| S07 | Resolved | An overly broad offline test matched a setup filename inside an error message |
| S08 | Planned Stage 2 | GenAI, RAG, agent, MCP, learner-data app and deployment/governance modules |
| S09 | Fixed, live verified | MLflow import used old runtime-loaded typing_extensions after dependency installation |
| S10 | Fixed, live verified | Rerun ownership check used a non-existent `routine_comment` column |
| S11 | Fixed, live verified | Unity Catalog model tag keys reject `.`; course MLflow/model tags now `a8learn_course`, `a8learn_tag` |
| S12 | Fixed, not live verified | `FileNotFoundError` from `pkgutil` after a Git folder merge: Python's working folder had been replaced |
| S13 | Implemented | Code cells did not explain themselves; Modules 0–3 and cleanup rewritten with WHAT/LOOK FOR comments |
| S14 | Implemented | First-time learners did not know how to clone, pull or recover from Git conflicts |
| S15 | Fixed | Interactive serving cell failed: the session's Databricks SDK requires `name` in `EndpointCoreConfigInput` |
| S16 | Fixed, live verified | Notebook cells mixed several operations, used a private SQL placeholder dialect and hid checks in bare assertions |
| S17 | Fixed, live verified | Serverless rejected `DataFrame.cache()` as unsupported `PERSIST TABLE` during Spark scoring |
| S18 | Implemented, not live validated | Module 1b descriptive AI/BI dashboard and Genie path; UI steps follow documentation, not a workspace walkthrough |
| S19 | Open | Genie Spaces are renamed Genie Agents in current documentation; workspace labels, Free Edition availability and Verified answer behaviour are unconfirmed |
| S21 | Fixed, not live verified | Module 1b's opt-in widget was not visible to the learner: the cell created it then raised an error; now a separate gate cell, as in Modules 0, 2 and 3 |
| S20 | Intentional | Cleanup notebook drops the reporting view but cannot delete dashboard drafts, Genie spaces or conversations; learners delete those manually by exact URL/ID |
| S23 | Implemented, not live validated | Module 1c diagnostic analytics: drill-downs, mix versus rate, permutation test and a Genie "why" check; offline only |
| S22 | Implemented, not live validated | Module 1b now starts with a short manual dashboard, then an opt-in learner-bound `.lvdash.json` file; workspace file recognition and import need learner observation |

## S01: persistent settings

**Symptom:** the pilot's lesson 1 received a blank catalog after running setup via `%run`.
**Cause:** widgets are notebook-scoped and are not a reliable shared settings store.
**Fix:** setup saves non-secret JSON under the current user's workspace folder; `_config` loads it,
validates the current identity and redeclares SQL session variables. It never reruns setup.
**Evidence:** separate live setup and lakehouse notebook tasks passed with the same selected namespace/tag.
**Limit:** rendered interactive UI still requires sign-in for visual inspection.

## S02: notebook-first learning

Code now shows the native SQL/PySpark, MLflow and SDK operations rather than wrapping a small fixture
in opaque helpers. Each module includes concepts, UI links/alternatives, checked tasks and a recap.
The full curriculum is in the short overview; later modules are explicitly labelled planned.

## S03–S05: release limits

Get approved brand assets before public release. Azure must be reauthenticated by the user using
browser OAuth, not a personal access token. The embedded browser session is separate from CLI OAuth;
no credentials or login state are copied between them. Live API execution is not a UI usability test.

## S06: governance evidence

The copy is deliberately filtered to Leeds/Online for all users, with a mask all users can observe.
The learner still owns the source. This demonstrates policy enforcement, not a production entitlement design.
Comments/tags describe data but do not grant/restrict access. System table permissions are optional.

## S07: offline test correction

The initial no-setup-rerun test rejected any occurrence of `00_setup`, including a helpful error message.
The check now tests for actual `%run ./00_setup` or `Course.save` calls. All 22 tests then passed.
No production behaviour or expected data value was relaxed.

## S18–S20: descriptive analytics module

**Scope:** one opt-in, ownership-guarded `event_metrics` view, one row per event. Bookings and feedback are
aggregated separately before joining, so feedback cannot multiply tickets. Revenue is not reported because
there is no payment ledger. Dashboard and Genie setup is learner-triggered, with no AI calls from the notebook.
S22 adds an optional dashboard-file write and a read-only SDK object-type lookup.
**Checks:** `tests/test_descriptive.py`, offline only.
**Uncertainty:** labels, Genie availability, generated SQL and benchmark behaviour need one approved live
checkpoint on Free Edition. Until then checkpoints D and G are unverified.

## S21: hidden reporting-view widget

**Symptom:** in the first learner test, the view cell raised "No view written" and no widget appeared above the
notebook. `dbutils.widgets.getAll()` showed `create_reporting_view = no`, so the widget existed but was not shown.
**Cause, likely:** unlike every other notebook, one cell both created the widget and raised an error.
**Fix:** a separate cell creates the gate widget and finishes normally; the create cell skips the write when it
is no, and an `A8.require` check then stops with a named missing view. Offline tests cover default-no and cell order.
**Limit:** the widget display has not been re-observed in the workspace yet.

## S22: shorter dashboard build and portable definition

**Need:** teach datasets, counters and field filters without spending the whole lesson configuring widgets.
**Change:** build one dataset, one counter and one city filter manually, then opt in to generating a complete
dashboard file from `dashboards/event_snapshot.lvdash.template.json`. Only the learner's reporting-view SQL is
inserted. The file is saved beside their settings, never intentionally replaced, and its workspace object type
is read using native SDK authentication. If stored as FILE rather than DASHBOARD, use the documented UI import.
No API creation, publishing, sharing, scheduling or AI requests are added. API dashboard deployment and Genie
creation belong to planned Module 8; Module 7 uses the conversation API with an existing Genie space.
**Checks:** offline execution covers the generated SQL, dataset/widget field bindings, default-no, existing-file
preservation and user-folder path. These checks do not prove UI rendering, filter interactivity or import.
**Remaining uncertainty:** whether a notebook-written file is recognised as DASHBOARD, exact UI import behaviour
and the supplied widget specs still need live observation. Cleanup remains manual by exact path/URL/ID.

For new issues record symptom, scope, evidence/cause, fix or blocker, checks and remaining uncertainty.
Never include credentials, private logs or personal workspace paths.

## S12: vanished working folder

**Symptom:** in an interactive Git folder, after resolving a merge and pulling, Module 3's import cell failed
with `FileNotFoundError: [Errno 2]` inside `pkgutil.get_importer`, with no filename.
**Cause:** the `''` entry on `sys.path` means the working folder; the merge had replaced that folder, so
`os.getcwd()` failed while an import scanned the path. Resetting the environment cleared it.
**Fix:** `_config` and `00_setup` fall back to the notebook path from the Databricks context and `os.chdir`
into the folder by path. **Limit:** the stale-folder case has not been reproduced live.

## S13: explaining code to learners

Learner feedback: dense cells mixed course safety checks with the Databricks concepts and had no explanation.
Module 3 now starts every code cell with WHAT/LOOK FOR comments, comments the key lines, adds predict prompts,
explains the expected pip warning, and moves experiment/model ownership checks into tested helpers
(`claim_experiment`, `mark_experiment`, `claim_model`). Modules 0–2 and cleanup now follow the same pattern,
and Module 1 introduces the `A8` helpers in a table before they are used.

## S14: Git folders for beginners

The author, new to Databricks, hit three Git problems in one session: obsolete notebooks kept after a pull,
an unclear conflict screen, and conflict markers written into a notebook. `docs/git-folders.md` now explains
clone, pull, discard and recovery in plain terms, with a symptom table. `README.md`, `START_HERE.md`, the overview
and `00_setup` link to it. UI labels follow the Databricks documentation and the author's screenshots;
the guide has not been walked through by a new learner.

## S17: serverless Spark scoring cache

**Symptom:** the first code-standard live run passed setup, data and governance, then both ML attempts failed
at `.cache()` with `[NOT_SUPPORTED_WITH_SERVERLESS] PERSIST TABLE is not supported`.
**Fix:** removed caching. A single aggregation now checks row count and probability validity; the small scoring
batch is evaluated once for those checks and once for the append. Later display and serving checks read the
persisted Delta batch instead of invoking the model again.
**Evidence:** the failure was reproduced in run `190892132722849`; automatic cleanup passed. Run
`208516018796520` then passed Spark scoring, serving, a second training/scoring run, acceptance and both cleanups.

## S16: copyable notebook code standard

**Symptom:** learner review found that a scoring cell combined model loading, validation, pandas conversion,
table/view writes and display. Other cells used `{events}` placeholders and bare `assert`, which are not
patterns to copy into production notebooks.
**Fix:** `docs/code-standard.md` now defines one idea per cell, native Spark/Databricks operations,
`IDENTIFIER(a8_*)` in `%sql` and exercises, real validated names in Python, imports at module top, and separate
`A8.expect` check cells. Module 3 scores with `mlflow.pyfunc.spark_udf`, appends `model_version`/`scored_at`,
and selects the latest score per booking in the forecast. Ruff runs in the offline unit tests.
**Evidence:** 37 offline tests cover exercise SQL, temporal splitting, real model probabilities and lint. Live run
`208516018796520` passed every notebook, two training/scoring batches, latest-per-booking acceptance, serving and
repeated cleanup. No smoke4 objects or generated workspace files remain.
**Limit:** migration of a prediction table created by the older course version is handled explicitly but was not
separately reproduced live; the live rerun started with the new schema.

## S15: serving config name

**Symptom:** in an interactive serverless session, the optional serving cell raised an error building
`EndpointCoreConfigInput`; the learner fixed it by adding `name=A8.endpoint_name`.
**Cause:** SDK versions differ between interactive and job environments. In some (including 0.73) `name` is a
required field of the config; the job environment's version made it optional, so live job runs passed.
**Fix:** always pass the endpoint name in the config. An offline test builds the config with the installed SDK.

## S09: notebook environment compatibility

The first live ML run (and its platform retry) stopped at import: a newly resolved Pydantic dependency
needed `typing_extensions.Sentinel`, but Python still held the older runtime module.
The upstream typing_extensions changelog confirms Sentinel is available from 4.14.
Explicitly install 4.15.0 and restart Python before loading configuration/importing MLflow.
Cleanup/acceptance notebooks install their own skinny client too; notebook-scoped packages do not
carry over to a different notebook. No monkey patch or runtime-global installation is used.
Retest from a fresh serverless notebook session.

## S10: rerun of the governance notebook

The second live run reused `a8_smoke_*` objects left by the first, failed run. The ownership-marker
check for SQL functions queried `information_schema.routines.routine_comment`; the column is `comment`.
First runs never reach that path, which is why the first governance run passed. Fixed in
`lib/a8learn/__init__.py` and retested through a full live rerun on existing objects.

## S11: model tag keys

Creating the registered model failed: `Tag key contains reserved characters (., =, >, <, %, &, ?, \)`.
Training and experiment tracking had already succeeded. MLflow experiment, run and UC model tags now use
underscores, matching the serving endpoint tags. Delta table properties keep `a8learn.course`, which Delta accepts.
The earlier smoke experiment was soft-deleted with old-style tags; the notebook correctly refuses to adopt it,
so the retest uses a new tag rather than weakening the ownership check.

## S23: diagnostic analytics module

**Scope:** Module 1c reads `event_metrics` only. It writes nothing and makes no AI call. The optional Genie "why" question is learner-triggered.
**Checks:** `tests/test_diagnostic.py`, offline only; Spark/serverless execution and Genie behaviour are not live validated.
**Limits:** the online gap is a pattern, not a proven cause. In this data online is both a city and a format, so they
cannot be separated, and only 48 completed events (15 online) support the comparison. Confounder adjustment and
Simpson's paradox are deferred. The failure modes listed for Genie are expected risks, not observed results.
