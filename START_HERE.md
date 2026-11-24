<img src="docs/assets/a8-logo.png" alt="Analytics8 logo" width="260">

# A8 | Databricks, from data to working AI

**The course is in the Databricks notebooks, not a separate website.**

1. Open this repository as a Databricks **Git folder**. New to Git? Follow
   [Git folders for beginners](docs/git-folders.md): clone once, pull for updates, never push.
2. Open [`notebooks/00_setup.py`](notebooks/00_setup.py), select Serverless compute and follow its cells.
3. Continue with `01_lakehouse_data` and `02_governance`, then climb the analytics levels: `03_descriptive_analytics`,
   `04_diagnostic_analytics`, `05_predictive_ml` and `06_prescriptive_analytics`.
   `07_genai` and `08a_embeddings` are optional and make no model request unless you approve it.
4. Before leaving, open `99_pause_and_cleanup`, especially if you created a serving endpoint.

Allow 30–45 minutes for setup and about an hour per lesson. Code, concepts, UI links,
UI alternatives, exercises, hints and solutions are together inside each notebook.
No local CLI, Python installation or coding assistant is needed for learners.
All data is synthetic. Never substitute customer data.

**Stage 1 implements Modules 0–2 and the analytics ladder in Modules 3–6.** The notebooks follow the order of
analytical complexity: descriptive (3), diagnostic (4), predictive (5), then prescriptive (6).
Modules 3, 4 and 6 are supplied and offline checked, **not live validated**.

Module **7** (GenAI) interprets five synthetic feedback comments. It is supplied and offline checked, **not live
validated**. Each model request needs separate approval and may use quota or incur charges; the SQL-only exercises
need none. Nothing is written.

Module **8a** (embeddings) turns the 27 distinct feedback comments into vectors, first by hand and then with a
Foundation Model embedding endpoint, and compares keyword and similarity search. It is supplied and offline checked,
**not live validated**. The embedding request needs your approval and writes nothing. RAG over documents follows in 8b.

Module **3** adds a Free Edition-first descriptive AI/BI dashboard and Genie learning path.
It builds one tagged event-metrics view, then guides you through a private dashboard draft
and a Genie space (called **Genie Agent** in newer UIs). Both use your existing SQL warehouse.
SQL-only fallback is available if a UI feature is blocked; it does not count as completing that feature.
Read the opt-in, quota and AI-request notices before running or creating anything; do not publish or share.

Module **4** adds diagnostic analytics: drill-downs, mix versus rate, a seeded permutation test and a
"why" question for your Module 3 Genie space. It reads `event_metrics` only, writes nothing and does not prove causation.

Module **5** adds predictive analytics: attendance probabilities and expected turnout, with MLflow evidence.

Module **6** adds prescriptive analytics: seeded simulation and expected-cost search for overbooking and catering
decisions over Module 5's predictions. It is read-only, uses assumed teaching costs and needs Module 5 first.

The [analytics-level map and full curriculum](docs/index.md) distinguish descriptive (3), diagnostic (4),
predictive (5) and prescriptive (6) analytics. Modules 7 onwards add AI capabilities (GenAI functions, RAG, agents,
MCP, an app using your learner tables, deployment and governance). They support the same levels rather than adding new
ones, and each will say which level it serves. Automation is planned in Modules 9 and 12.
These later modules are planned, not supplied yet. The earlier fixture-based app has been removed.

**Start in Free Edition, fall back to paid.** Clone the course into each workspace you have. Work through it in
Free Edition first. If a step is blocked by a missing feature, a quota or a permission, repeat that lesson in your
paid workspace: run `00_setup`, then `01_lakehouse_data`, then the lesson that was blocked. Tables, models and saved
settings are per workspace and do not carry over.

Free Edition defaults to `workspace.default`. On a paid workspace, enter a catalog and schema you have been given
permission to write to; the course never creates schemas. Use a unique learner tag.
Settings are saved once in your workspace user folder and reloaded by each notebook.
Compute/storage and optional serving can cost money. Free Edition has usage quotas.
Serving and Module 3's reporting-view write are opt-in; dashboard/Genie UI writes and AI requests are learner-triggered.
Maintainers: Python 3.12, `python -m pip install -r requirements-dev.txt`,
`python -m unittest discover -s tests -v`, then `python -m mkdocs build --strict`.
See [validation](docs/validation.md) and [known issues](docs/issues.md) for actual evidence and limitations.
This independent repository does not modify the adjacent original training project.
