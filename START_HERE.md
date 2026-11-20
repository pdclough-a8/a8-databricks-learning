<img src="docs/assets/a8-logo.png" alt="Analytics8 logo" width="260">

# A8 | Databricks, from data to working AI

**The course is in the Databricks notebooks, not a separate website.**

1. Open this repository as a Databricks **Git folder**. New to Git? Follow
   [Git folders for beginners](docs/git-folders.md): clone once, pull for updates, never push.
2. Open [`notebooks/00_setup.py`](notebooks/00_setup.py), select Serverless compute and follow its cells.
3. Continue with `01_lakehouse_data`, `01b_descriptive_analytics`, `01c_diagnostic_analytics`, `02_governance`, then `03_predictive_ml` and `01d_prescriptive_analytics`.
4. Before leaving, open `99_pause_and_cleanup`, especially if you created a serving endpoint.

Allow 30–45 minutes for setup and about an hour per lesson. Code, concepts, UI links,
UI alternatives, exercises, hints and solutions are together inside each notebook.
No local CLI, Python installation or coding assistant is needed for learners.
All data is synthetic. Never substitute customer data.

**Stage 1 implements Modules 0–3.** Module **1b** adds a Free Edition-first descriptive
AI/BI dashboard and Genie learning path, supplied but **not live validated**.
It builds one tagged event-metrics view, then guides you through a private dashboard draft
and a Genie space (called **Genie Agent** in newer UIs). Both use your existing SQL warehouse.
SQL-only fallback is available if a UI feature is blocked; it does not count as completing that feature.
Read the opt-in, quota and AI-request notices before running or creating anything; do not publish or share.

Module **1d** adds prescriptive analytics: seeded simulation and expected-cost search for overbooking and catering
decisions over Module 3's predictions. It is read-only, uses assumed teaching costs, and is supplied and offline checked,
not live validated. Run it after Module 3.

Module **1c** adds diagnostic analytics: drill-downs, mix versus rate, a seeded permutation test and a
"why" question for your Module 1b Genie space. It reads `event_metrics` only, writes nothing and does not prove causation.
It is supplied and offline checked, not live validated.

The [analytics-level map and full curriculum](docs/index.md) distinguish descriptive (1b), diagnostic (1c), predictive (3)
and prescriptive (1d) analytics. Automation is planned in Modules 6 and 8;
platform, governance, GenAI and retrieval capabilities support these levels.
The later curriculum includes GenAI functions,
RAG, agents, MCP, an app using your learner tables, deployment and governance.
These later modules are planned, not supplied yet. The earlier fixture-based app has been removed.

Free Edition defaults to `workspace.default`. Azure paid defaults to `users.pclough`,
without creating schemas. Use a unique learner tag and existing authorised schema.
Settings are saved once in your workspace user folder and reloaded by each notebook.
Compute/storage and optional serving can cost money. Free Edition has usage quotas.
Serving and Module 1b's reporting-view write are opt-in; dashboard/Genie UI writes and AI requests are learner-triggered.

Maintainers: Python 3.12, `python -m pip install -r requirements-dev.txt`,
`python -m unittest discover -s tests -v`, then `python -m mkdocs build --strict`.
See [validation](docs/validation.md) and [known issues](docs/issues.md) for actual evidence and limitations.
This independent repository does not modify the adjacent original training project.
