---
name: lean-databricks-module
description: Deliver one scoped Databricks course module with explicit outcomes, a token budget, targeted validation, and one approved live checkpoint. Invoke when starting a new module in this repository.
user-invocable: true
disable-model-invocation: true
---

# Lean Databricks module

Deliver one vertical learning slice. Databricks is the subject; event management is the case study.

## 1. Agree the contract before editing

State concisely:

- learning outcomes and the Databricks capabilities taught;
- the single module or vertical slice in scope;
- explicit non-goals and features deferred;
- files likely to change, reusing existing data and course plumbing;
- target workspace and any cloud resources, charges or approvals;
- targeted checks, final checks and live evidence required;
- the user's token budget and stopping point.

If outcomes, scope or budget are missing, ask before implementation. Do not expand the slice without approval.

## 2. Keep exploration and implementation small

- Use focused searches and file slices. Avoid rereading whole notebooks or broad repository exploration.
- Prefer focused edits over complete-file rewrites.
- Do not use subagents, Missions or workstreams without explicit approval.
- Fetch only the specific documentation needed. Do not paste large logs or documentation into the session.
- Preserve the code standard, ownership guards, cost gates and scoped cleanup.

## 3. Validate economically

- Run targeted checks while developing and address failures from their actual output.
- Do not repeat a passing check unless a later change affects it.
- At completion, run the repository's required offline unit suite and strict documentation build once.
- Run at most one integrated live validation for the stage, only with explicit approval.
- Use a single status watcher for live work. Do not poll independently as well.
- Ask before another live rerun or broader validation instead of repeating automatically.

## 4. Finish with evidence and a handoff

- Record actual checks, skipped checks and limitations in the course evidence files.
- Commit and push only when authorised.
- Report changed files, evidence, remaining limitations and the next small decision.
- At the agreed token budget, stop safely and hand off rather than continuing automatically.

## Definition of done

The contracted learning path works, required safeguards remain, final checks have run once, evidence is recorded,
and no unapproved cloud resources or scope expansion remain.
