# Notebook code standard

Course notebooks are read by beginners and copied into real projects, so the code has to be worth copying,
not just correct. These rules apply to every lesson notebook. Library code in `lib/a8learn` follows normal
Python practice and the same lint settings.

## Rules

1. **One idea per cell.** A code cell does one thing a learner can name: load, transform, write, check or show.
   Aim for 15 lines or fewer. If a cell needs "and then" to describe it, split it.
   Exception: one **setup cell** per notebook may hold the imports, prerequisite check and name resolution,
   ending in a single "Ready" line, so learners are not walked through several empty cells.
2. **Standard Databricks first.** Use Spark DataFrames, `spark.table`, `spark.sql`, `%sql` cells, MLflow and the
   Databricks SDK as their documentation shows them. Prefer Spark for data work. Where a data scientist would naturally use pandas or the Python SDK, add a labelled
   `PYTHON ROUTE` cell that builds the same result and checks it against the SQL result; say why pandas is fine
   (small tables, a library that needs it). Exercises accept SQL, Spark and pandas answers.
3. **No private SQL dialect.** Write SQL that would run in the SQL editor:
   - In `%sql` cells and exercises, refer to course objects with session variables: `IDENTIFIER(a8_events)`.
   - In Python, build names once (`events = A8.t("events")`) and use f-strings. Names are validated by the
     course configuration, so they are safe to interpolate. Values go in as `spark.sql(..., args={...})` parameters.
   - Saved views cannot reference variables or parameters, so their SQL uses the real names, built in Python.
4. **Helpers only for course plumbing.** `A8` helpers exist for settings, names, ownership checks, UI links and
   exercise checking. They never hide a Databricks operation the lesson is teaching.
5. **Checks are explicit and separate.** Validation goes in its own "Check" cell using `A8.expect(condition, message)`,
   which raises a clear error. A prerequisite check may sit in the setup cell. Do not use bare `assert` for runtime checks: Python can skip it, and its failure says nothing.
6. **Each cell reads on its own.** A cell may use variables from earlier cells in the same section; anything from
   further back is named in the section's text. Rerunning a cell must not drift data (no repeated `+ 1`).
7. **Imports at the top of the module**, in one commented cell after `%run ./_config`. Exception: the optional serving
   section imports its SDK classes inside the opt-in block, so learners who skip it never load them.
8. **Comments say why, not what.** Each Python code cell opens with `# WHAT:` (purpose) and `# LOOK FOR:`
   (expected output). Magic-only `%run` and `%pip` cells use the adjacent Markdown explanation instead. Line
   comments explain a non-obvious choice or constraint, not what the next line plainly does.
9. **Realistic data patterns.** Writes are idempotent (`CREATE OR REPLACE`, `IF NOT EXISTS`). Prediction tables record
   `model_version` and `scored_at`. Never use `CREATE OR REPLACE` on an object the learner might not own: call
   `A8.guard` first.
10. **Linted like any code.** `ruff check lib notebooks tests` runs in the unit tests. Notebook-only exceptions are
    configured in `pyproject.toml`: Databricks injects `spark`, `dbutils` and `display`, `%run` defines `A8`, and
    imports after the configuration cell necessarily trigger Python's ordinary import-order rule.

## Reviewing a change

- Could a learner paste each SQL statement into the SQL editor, with only the names changed?
- Does every cell's `WHAT` line describe exactly one idea?
- Would the notebook still be correct if the learner ran one cell twice?
- Is every check in a Check cell, with a message that says what went wrong?
