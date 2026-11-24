![Analytics8 logo](assets/a8-logo.png){ .a8-logo }

# A8 | Databricks, from data to working AI

**Learn in the notebooks.** Open `notebooks/00_setup` in your Databricks Git folder.
The website is an overview and evidence ledger, not a second set of lesson instructions.

You run A8 Events. Use one continuous dataset: **60 events, 4,204 bookings and 395 feedback records**,
all synthetic, frozen at 20 November 2026. Each lesson explains a concept, demonstrates a real
Databricks operation, takes you into the UI, gives checked exercises and finishes with a recap.
Allow about an hour per lesson, plus deployment waits. These are planning estimates, not measured learner timings.

## The analytics levels

The levels describe the question you are answering, not a ladder of Databricks products.
Using an LLM does not automatically make an answer predictive or prescriptive.

| Level | Question | Course home |
|---|---|---|
| Descriptive | What happened, or what is booked? | Module 3: dashboard and SQL-checked Genie answers |
| Diagnostic | Why did it happen? | Module 4: drill-downs, mix versus rate and a chance test; association alone is not causation |
| Predictive | What is likely to happen? | Module 5: attendance probabilities and expected turnout |
| Prescriptive | What should we do, given objectives and constraints? | Module 6: choose ticket limits and meal orders |
| Automation | How can approved work run repeatedly or take bounded actions? | Modules 9 and 12, planned |

The course follows the order of analytical complexity: Modules 0–2 provide the platform, data and governance
foundations, then Modules 3–6 climb from descriptive to diagnostic, predictive and prescriptive analytics.
Modules 7–11 add AI capabilities (GenAI functions, retrieval, agents, MCP and an app). They support the same four
levels, for example GenAI classifying feedback for a descriptive question or an agent acting on a prescriptive
recommendation, but they are not new levels. Each AI module names the level it serves and states what the model adds
that a query or a classical model does not. Automation is a delivery capability, not proof of better analysis.

## Full curriculum

| Module | What you build and learn | Delivery |
|---|---|---|
| 0. Workbench | Git folders, compute, catalog/schema, permissions and persistent configuration | Stage 1 |
| 1. Lakehouse data | Volumes, `read_files`, typed Delta tables, SQL and PySpark, joins, views, history/time travel, lineage | Stage 1 |
| 2. Governance | Grants and identity, comments/tags, real row filters and column masks, lineage and optional audit system tables | Stage 1 |
| 3. Descriptive AI/BI and Genie | Event-grain reporting view, metrics, draft dashboard datasets/charts/filters, Genie instructions/examples and SQL-checked answers | Supplied; offline checked, no live validation |
| 4. Diagnostic analytics | SQL drill-downs by city, topic, format and month; mix-versus-rate split of a gap; a seeded permutation test; a Genie "why" question checked against SQL; pattern versus cause | Supplied; offline checked, no live validation |
| 5. Predictive ML | Booking-time features, temporal holdout, baseline, MLflow evidence, UC model versions/aliases, batch inference and optional custom model serving | Stage 1 |
| 6. Prescriptive analytics | Overbooking and catering decisions: seeded Monte Carlo over Module 5 predictions, expected-cost search, cost and probability sensitivity, human-judgement checkpoint; read-only | Supplied (run after Module 5); offline checked, no live validation |
| 7. GenAI | Playground, `ai_query`, AI Functions for feedback comments (descriptive, five synthetic comments), human review; prompt registry and tracing deferred | Supplied; offline checked, no live validation; model requests opt-in |
| 8a. Embeddings | Vectors by hand (bag of words, cosine similarity), keyword versus similarity search, real embeddings from a Foundation Model endpoint behind a default-no switch; nothing written | Supplied; offline checked, no live validation |
| 8b. RAG by hand | A fictional nine-document knowledge base copied to your volume, chunked by section, stored in a Delta table, retrieved by word overlap and by embeddings, a grounded and cited prompt, a refusal case and a hit-at-k retrieval evaluation; the embedding and chat requests sit behind default-no switches | Supplied; offline checked, no live validation |
| 8c. Vector Search | Managed embeddings and a Vector Search index over the chunk table, swapped in for the hand-built retriever; index build time, billing and cleanup | Planned next |
| 9. Agent | UC functions as tools, structured tool calls, constrained actions and traces | Planned next |
| 10. MCP | Model Context Protocol clients/servers, Databricks managed MCP, authentication and tool boundaries | Planned next |
| 11. Interactive app | Streamlit on Databricks Apps, query **your UC tables**, Genie conversation API over an existing space, grounded answers, resources, service principal versus user identity, grants, logs and redeployment | Planned next |
| 12. Deploy and govern | Declarative Automation/Asset Bundles, jobs, dashboard deployment and programmatic Genie creation, dev→prod configuration, Unity/AI Gateway capabilities, cost, evaluation/release gates and rollback | Planned next |
| 99. Lifecycle | Pause/resume, endpoint deletion and exact scoped cleanup | Stage 1; extends with later modules |

## Start and stop

First time in Databricks? [Git folders for beginners](git-folders.md) shows how to clone the course,
pull updates and recover from conflicts.

Use the notebook file browser: `00_setup` → `01_lakehouse_data` → `02_governance` → `03_descriptive_analytics` → `04_diagnostic_analytics`
→ `05_predictive_ml` → `06_prescriptive_analytics` → `07_genai` (optional) → `08a_embeddings` (optional) → `08b_rag` (optional) → `99_pause_and_cleanup`.

Keep the whole repository together. `_config` reloads saved settings; it is not a lesson.
Do not run all notebooks blindly: read the write/cost notices and opt in separately to serving.

## Module 3: descriptive analytics, not prediction

Build a private **draft** AI/BI dashboard and a Genie space over the same learner-tagged event metrics.
Start with one dataset, one counter and one city filter by hand, then opt in to generating a learner-bound
`.lvdash.json` file for the complete dashboard. API creation/deployment is deferred to Module 12.
The notebook supplies native SQL, a dashboard template, metric definitions, three example question/SQL pairs,
three held-out SQL checks, a human-reviewed boundary question and two checked exercises.
Current Databricks documentation calls Genie Spaces **Genie Agents**; this lesson uses their Chat mode,
not Genie Code or multi-step Agent mode. It does not replace the later custom agent module.

Free Edition is the first route: existing serverless compute and SQL warehouse, no new warehouse,
schema, endpoint, schedule or paid trial. The view write defaults to no. UI creation/configuration and AI
requests and the optional dashboard-file write need deliberate learner approval.
Keep the draft/space in your own folder, inspect inherited
access and do not publish, share or change permissions.

The supplied SQL is checked offline; dashboard rendering/interactivity, Genie quality and workspace
compatibility are **not live validated**. If a UI feature is unavailable, use the labelled SQL-only
fallback and record that checkpoint as blocked. Exact UI-asset cleanup is manual; the cleanup notebook
drops the reporting view but does not delete generated files, dashboard drafts, Genie spaces, conversations or caches.

## Module 4: diagnostic analytics, not causation

Explain why completed online events attend less than in-person and hybrid ones, using the Module 3
`event_metrics` view. You drill down by city, topic, format and month, split the gap into a **mix** effect
(different kinds of events) and a **rate** effect (same kind, different behaviour), and run one seeded permutation test
(numpy, no new library) to ask whether the gap is bigger than chance. Then you ask your existing Genie space a
"why" question and check its SQL and prose against the reference. Two checked exercises follow the 3 style.

The notebook states plainly that nothing in it proves causation. It writes nothing, deploys nothing and makes no AI call.
The optional Genie step is learner-triggered and needs approval. Confounder adjustment and Simpson's paradox are deferred.

## Module 6: prescriptive analytics, assumptions not guarantees

Decide how many tickets to sell and how many meals to order for one scheduled event, using the Module 5
`attendance_predictions` table and `event_forecast` view. A seeded numpy simulation draws plausible turnouts, an
expected-cost search finds the cheapest choice, and sensitivity tables show how fragile it is. Costs are **assumed
teaching parameters**, bookings are treated as independent, and the model's probabilities are trusted as given.
Nothing is written, no library is added and no model is called. Two SQL exercises and a human-judgement checkpoint
on fairness to turned-away attendees complete it. Run it after `05_predictive_ml`.

## Module 7: GenAI reads feedback text, descriptive not predictive

Interpret five synthetic feedback comments with `ai_analyze_sentiment` and `ai_classify` (version 2.1), then optionally
send one explicit `ai_query` prompt to an endpoint you name. Compare sentiment with ratings as a sanity check, not accuracy.
A one-use, default-no gate guards each model request, every request needs a recorded scope and cost/quota note, and nothing
is written or persisted. Free Edition limits, region, pricing and model availability vary and are not verified live.
Two model-free SQL exercises work with every gate closed. RAG, agents and tracing are later modules.

## Workspace boundaries

- **Free Edition:** existing `workspace.default`, serverless compute, quotas and feature restrictions apply.
- **Paid (AWS, Azure or Google Cloud):** a catalog and schema you have been given; no schema creation. Your administrator controls availability and grants.
- **Order of use:** start in Free Edition. If a step is blocked, repeat that lesson in the paid workspace (run `00_setup` and `01_lakehouse_data` there first). Each workspace has its own tables, models and settings.
- Namespace all artefacts with your learner tag. Never use shared tables for experimentation.
- Data, MLflow and model versions persist. Optional serving endpoints can bill after closing a notebook; delete them.
- A model alias is not approval. A mask is not anonymisation. A completed notebook is not production validation.
- Dashboard filters and Genie instructions are not access controls; Module 2 teaches enforcement.

The previous three-lesson pilot and packaged-fixture app have been superseded, not left as alternative instructions.
The future app will read learner data; it is not included in Stage 1.
See [validation evidence](validation.md), [known issues](issues.md) and [brand application](brand.md).
