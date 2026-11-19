# A8 | Data to working AI

Build an Event Operations Assistant you can check, explain and hand over.

**Pilot v0.1.0**, readiness plus three connected lessons, with UI-led and code-first routes.
Start with [the course guide](docs/index.md), then [readiness](docs/start.md).
Use the Markdown guide directly or build the course site.

- Learners: a browser and an authorised Databricks workspace. No local Python, CLI or AI coding subscription required.
- Maintainers: Python 3.12 or 3.13; `python -m pip install -r requirements-dev.txt`,
  `python -m unittest discover -s tests -v`, then `python -m mkdocs build --strict`.
- Optional local simulation: install `app/event_assistant/requirements.txt`, change directory to
  `app/event_assistant`, then run `python -m streamlit run app.py`. No credentials needed in simulation.

This is an independent course, not a replacement of the adjacent original training.
The existing tracked deletion of `README.md` has been preserved.
No GitHub remote, hosted course URL or deployment is created by these files.
See [validation](docs/validation.md) before teaching: local checks are not evidence of a live Databricks run.
