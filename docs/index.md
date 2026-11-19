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

Use the notebook file browser: `00_setup` → `01_lakehouse_data` → `02_governance`
→ `03_predictive_ml` → `99_pause_and_cleanup`.
Keep the whole repository together. `_config` reloads saved settings; it is not a lesson.
Do not run all notebooks blindly: read the write/cost notices and opt in separately to serving.

- **Free Edition:** existing `workspace.default`, serverless compute, quotas and feature restrictions apply.
- **Azure paid:** existing `users.pclough`; no schema creation. Your administrator controls availability and grants.
- Namespace all artefacts with your learner tag. Never use shared tables for experimentation.
- Data, MLflow and model versions persist. Optional serving endpoints can bill after closing a notebook; delete them.
- A model alias is not approval. A mask is not anonymisation. A completed notebook is not production validation.

The previous three-lesson pilot and packaged-fixture app have been superseded, not left as alternative instructions.
The future app will read learner data; it is not included in Stage 1.
See [validation evidence](validation.md), [known issues](issues.md) and [brand application](brand.md).
