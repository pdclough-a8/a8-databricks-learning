# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read first

Read `AGENTS.md` (hard rules: no credentials, no cloud writes/deployment/paid model calls without explicit approval,
work only in this repo, lean sessions, no subagents without approval) and `prompts/tutor.md` (only if acting as the
optional learner tutor; the course does not require it). `docs/code-standard.md` governs all notebook code.

## What this is

A notebook-first Databricks course (synthetic "A8 Events" case study). Learners clone the repo as a Databricks Git
folder and work inside `notebooks/`; there is no app to build. Python is `>=3.12,<3.14`; dev dependencies are in
`requirements-dev.txt` (a vendored `.packages/` folder is git-ignored and used for local runs).

## Commands

```
python -m unittest discover -s tests -v          # full offline suite (also runs ruff)
python -m unittest tests.test_ml -v              # one module's tests
python -m unittest tests.test_stage1.ConfigTests.test_validation   # a single test
python -m ruff check lib notebooks tests         # lint (line length 120)
python -m mkdocs build --strict                  # docs build; must pass
python data/generate.py                          # regenerate data/raw/*.csv (seeded, must stay byte-identical)
```

Run the unit suite and strict docs build once at completion of a change. `tests/live_smoke.py` and
`tests/acceptance_notebook.py` are maintainer-only live runs against the `a8-free` workspace: never run them without
explicit approval, and never from unit tests. Record validation limits in `docs/validation.md` and `docs/issues.md`.

## Architecture

- **`notebooks/*.py`** are Databricks source-format notebooks (`# Databricks notebook source`, `# COMMAND ----------`,
  `# MAGIC` cells). Numbered by the analytics ladder: 00 setup, 01 data, 02 governance, 03 descriptive, 04 diagnostic,
  05 predictive ML, 06 prescriptive, 07 GenAI (optional), 99 pause/cleanup. Each starts with `%run ./_config`.
- **`notebooks/_config.py`** locates the repo root, puts `lib/` on `sys.path`, loads the learner's saved settings
  JSON (not widgets, which do not survive `%run`) and exposes the `A8` object (`a8learn.Course`).
- **`lib/a8learn/__init__.py`** is the shared plumbing: `Config`/`Course`, name derivation (`a8_<tag>_<key>`, via the
  `OBJECTS` registry mapping logical object -> type and creating module), ownership guards (`A8.guard`, `A8.require`),
  `A8.expect` checks, exercise checking, and default-no `A8.gate` switches for cloud actions. Nothing runs a cloud
  action at import time.
- **`lib/a8learn/exercises.py`** holds every SQL exercise (task, hint, solution, explanation); checked against the
  learner's own tables. **`lifecycle.py`** implements scoped cleanup used by `99_pause_and_cleanup`.
- **`data/generate.py`** deterministically produces `data/raw/*.csv` (seed 8, snapshot 2026-11-20); exercise answers
  depend on this, so do not change it casually. **`dashboards/`** holds a Lakeview template used by Module 3.
- **Tests** run offline with fakes: they parse notebook source (they do not execute `%run`/`%pip`/`%sql`), and
  `test_lint.py` runs ruff. Offline passing does not prove Databricks behaviour; live status is tracked in
  `docs/validation.md`.
- **`docs/` + `mkdocs.yml`** is a small meta-docs site (standards, validation, issues, brand), not the course itself.
  New docs pages must be added to `nav` or the strict build fails.

## Conventions that are easy to break

- Notebook cells: one idea per cell, opening `# WHAT:` / `# LOOK FOR:` comments, checks in separate cells using
  `A8.expect` (never bare `assert`), standard Spark/SQL (`IDENTIFIER(a8_events)` in `%sql`, `A8.t("events")` in Python,
  values via `spark.sql(..., args=)`), idempotent writes, `A8.guard` before `CREATE OR REPLACE` on anything the learner
  might not own. One setup cell per notebook ends in a single "Ready" line.
- Adding a course object means adding it to `OBJECTS` so cleanup and ownership checks cover it.
- Ruff per-file ignores for `notebooks/*.py` (F821, E402) are intentional: Databricks injects `spark`, `dbutils`,
  `display`, and `%run` defines `A8`.
- Plain UK English; A8 text branding only (palette values are provisional). Do not add the internal brand playbook,
  competitive intelligence, client lists or testimonials. All data is synthetic; never substitute customer data.
- Modules 3, 4, 6 and 7 are supplied and offline-checked but not live validated; say so rather than implying otherwise.
- `.factory/skills/lean-databricks-module` defines the one-module-per-session workflow for new modules.
- Databricks CLI profiles: pass `--profile` explicitly; never auto-select one.
