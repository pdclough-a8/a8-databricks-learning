<img src="docs/assets/a8-logo.png" alt="Analytics8 logo" width="260">

# A8 | Databricks, from data to working AI

**The course is in the Databricks notebooks, not a separate website.**

1. Open this repository as a Databricks **Git folder**. New to Git? Follow
   [Git folders for beginners](docs/git-folders.md): clone once, pull for updates, never push.
2. Open [`notebooks/00_setup.py`](notebooks/00_setup.py), select Serverless compute and follow its cells.
3. Continue with `01_lakehouse_data` and `02_governance`, then climb the analytics levels: `03_descriptive_analytics`,
   `04_diagnostic_analytics`, `05_predictive_ml` and `06_prescriptive_analytics`.
   `07_genai`, `08a_embeddings`, `08b_rag`, `08c_vector_search` and `09_agents` are optional and make no model request unless you approve it.
4. Before leaving, open `99_pause_and_cleanup`, especially if you created a serving endpoint.

Allow 30–45 minutes for setup and about an hour per lesson. Code, concepts, UI links,
UI alternatives, exercises, hints and solutions are together inside each notebook.
No local CLI, Python installation or coding assistant is needed for learners.
All data is synthetic. Never substitute customer data.

**Stage 1 implements Modules 0–2 and the analytics ladder in Modules 3–6.** The notebooks follow the order of
analytical complexity: descriptive (3), diagnostic (4), predictive (5), then prescriptive (6).
Modules 3, 4 and 5 ran end to end on Free Edition in a maintainer test (the dashboard and Genie parts of 3 and 4 were not
tested). Module 6 is supplied and offline checked, **not live validated**.

Module **7** (GenAI) interprets five synthetic feedback comments. It is supplied and offline checked, **not live
validated**. Each model request needs separate approval and may use quota or incur charges; the SQL-only exercises
need none. Nothing is written.

Module **8a** (embeddings) turns the 27 distinct feedback comments into vectors, first by hand and then with a
Foundation Model embedding endpoint, and compares keyword and similarity search. It is offline checked and its SQL
route was validated live on Free Edition (the Python route was not). The embedding request needs your approval and writes nothing. RAG over documents follows in 8b.

Module **8b** (RAG) answers customer questions from a fictional nine-document A8 Events knowledge base: it chunks the
documents, retrieves by word overlap and by embeddings, builds a grounded, cited prompt and scores retrieval. It is
offline checked and validated live on Free Edition. It writes nine files and one table; the embedding and chat
requests each need your approval. A managed Vector Search index follows in 8c.

**Choose your route.** Every lesson works in SQL. Where the analysis could be done in Python, a `PYTHON ROUTE` cell
(pandas, or the Databricks SDK in 8a) builds the same result and checks it against the SQL. Data scientists can start
from those cells and answer exercises with a DataFrame; analysts can follow the SQL. See `00_setup`, "Choose your route".

Module **8c** (Vector Search) creates a Vector Search endpoint and a managed Delta Sync index over the 8b chunk table,
queries it, compares it with the hand-built search and ends by deleting both. It is offline checked and validated live
on Free Edition. The endpoint **bills while it exists** and can take 15 to 20 minutes to become usable, so each create
and delete step needs your approval and `99_pause_and_cleanup` also removes them.

Module **9** (agents) builds a small agent that chooses between two read-only tools, with a step cap and a trace. It
needs the 8b chunk table, creates nothing, and its two model steps (a JSON decider and an optional native tool-calling one) are default-no switches. Supplied and offline checked,
**not live validated**.

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
