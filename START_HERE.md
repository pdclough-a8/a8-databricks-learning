# A8 | Databricks, from data to working AI

**The course is in the Databricks notebooks, not a separate website.**

1. Open this repository as a Databricks **Git folder**. New to Git? Follow
   [Git folders for beginners](docs/git-folders.md): clone once, pull for updates, never push.
2. Open [`notebooks/00_setup.py`](notebooks/00_setup.py), select Serverless compute and follow its cells.
3. Continue with `01_lakehouse_data`, `01b_descriptive_analytics`, `02_governance`, then `03_predictive_ml`.
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

The [full curriculum](docs/index.md) includes GenAI functions,
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
