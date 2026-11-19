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

For new issues record symptom, scope, evidence/cause, fix or blocker, checks and remaining uncertainty.
Never include credentials, private logs or personal workspace paths.

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
