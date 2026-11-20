# A8 | Databricks, from data to working AI

**Learn in the notebooks.** Open `notebooks/00_setup` in your Databricks Git folder.
The website is an overview and evidence ledger, not a second set of lesson instructions.

You run A8 Events. Use one continuous dataset: **60 events, 4,204 bookings and 395 feedback records**,
all synthetic, frozen at 20 November 2026. Each lesson explains a concept, demonstrates a real
Databricks operation, takes you into the UI, gives checked exercises and finishes with a recap.
Allow about an hour per lesson, plus deployment waits. These are planning estimates, not measured learner timings.

## Full curriculum

| Module | What you build and learn | Delivery |
|---|---|---|
| 0. Workbench | Git folders, compute, catalog/schema, permissions and persistent configuration | Stage 1 |
| 1. Lakehouse data | Volumes, `read_files`, typed Delta tables, SQL and PySpark, joins, views, history/time travel, lineage | Stage 1 |
| 1b. Descriptive AI/BI and Genie | Event-grain reporting view, metrics, draft dashboard datasets/charts/filters, Genie instructions/examples and SQL-checked answers | Supplied; offline checked, no live validation |
| 2. Governance | Grants and identity, comments/tags, real row filters and column masks, lineage and optional audit system tables | Stage 1 |
| 3. Predictive ML | Booking-time features, temporal holdout, baseline, MLflow evidence, UC model versions/aliases, batch inference and optional custom model serving | Stage 1 |
| 4. GenAI | Playground, pay-per-token endpoints, `ai_query`, AI Functions for feedback, prompts and tracing | Planned next |
| 5. RAG | Document/chunk tables, managed embeddings, Vector Search retrieval, grounded citations, refusal and MLflow evaluation | Planned next |
| 6. Agent | UC functions as tools, structured tool calls, constrained actions and traces | Planned next |
| 6b. MCP | Model Context Protocol clients/servers, Databricks managed MCP, authentication and tool boundaries | Planned next |
| 7. Interactive app | Streamlit on Databricks Apps, query **your UC tables**, grounded answers, resources, service principal versus user identity, grants, logs and redeployment | Planned next |
| 8. Deploy and govern | Declarative Automation/Asset Bundles, jobs, dev→prod configuration, Unity/AI Gateway capabilities, cost, evaluation/release gates and rollback | Planned next |
| 99. Lifecycle | Pause/resume, endpoint deletion and exact scoped cleanup | Stage 1; extends with later modules |

## Start and stop

First time in Databricks? [Git folders for beginners](git-folders.md) shows how to clone the course,
pull updates and recover from conflicts.

Use the notebook file browser: `00_setup` → `01_lakehouse_data` → `01b_descriptive_analytics` → `02_governance`
→ `03_predictive_ml` → `99_pause_and_cleanup`.
Keep the whole repository together. `_config` reloads saved settings; it is not a lesson.
Do not run all notebooks blindly: read the write/cost notices and opt in separately to serving.

## Module 1b: descriptive analytics, not prediction

Build a private **draft** AI/BI dashboard and a Genie space over the same learner-tagged event metrics.
The notebook supplies native SQL, chart/filter recipes, metric definitions, three example question/SQL pairs,
three held-out SQL checks, a human-reviewed boundary question and two checked exercises.
Current Databricks documentation calls Genie Spaces **Genie Agents**; this lesson uses their Chat mode,
not Genie Code or multi-step Agent mode. It does not replace the later custom agent module.

Free Edition is the first route: existing serverless compute and SQL warehouse, no new warehouse,
schema, endpoint, schedule or paid trial. The view write defaults to no. UI creation/configuration and AI
requests need deliberate learner approval. Keep the draft/space in your own folder, inspect inherited
access and do not publish, share or change permissions.

The supplied SQL is checked offline; dashboard rendering/interactivity, Genie quality and workspace
compatibility are **not live validated**. If a UI feature is unavailable, use the labelled SQL-only
fallback and record that checkpoint as blocked. Exact UI-asset cleanup is manual; the cleanup notebook
drops the reporting view but does not delete dashboard drafts, Genie spaces, conversations or caches.

## Workspace boundaries

- **Free Edition:** existing `workspace.default`, serverless compute, quotas and feature restrictions apply.
- **Azure paid:** existing `users.pclough`; no schema creation. Your administrator controls availability and grants.
- Namespace all artefacts with your learner tag. Never use shared tables for experimentation.
- Data, MLflow and model versions persist. Optional serving endpoints can bill after closing a notebook; delete them.
- A model alias is not approval. A mask is not anonymisation. A completed notebook is not production validation.
- Dashboard filters and Genie instructions are not access controls; Module 2 teaches enforcement.

The previous three-lesson pilot and packaged-fixture app have been superseded, not left as alternative instructions.
The future app will read learner data; it is not included in Stage 1.
See [validation evidence](validation.md), [known issues](issues.md) and [brand application](brand.md).
