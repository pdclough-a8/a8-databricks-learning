# A8 learning pilot

Work only in this repository. The adjacent original training is comparison material, not an edit target.
Never read, print or commit credentials. Browser OAuth and Databricks native workload authentication only.
No cloud writes, deployment, paid model calls or publishing without explicit approval.
Keep every cloud operation learner-triggered. Never change shared schemas, endpoints or unrelated objects.
Run `python -m unittest discover -s tests -v` and `python -m mkdocs build --strict`.
Notebooks follow `docs/code-standard.md`; the unit tests run `ruff check lib notebooks tests`.
Record validation limits and problems in `docs/validation.md` and `docs/issues.md`.

## Lean development

- Deliver one module or vertical slice per session. Agree outcomes, non-goals and a token budget before editing.
- Start new modules in fresh sessions. Invoke `/lean-databricks-module` before implementation.
- Use focused reads and edits. Avoid full-notebook rewrites, broad exploration, repeated polling and large log dumps.
- Do not use subagents, Missions or workstreams without explicit approval.
- Run targeted checks during development and the required offline unit/docs checks once at completion.
- Use one planned live validation per stage with approval. Ask before another live rerun.
- At the agreed token budget, stop safely and hand off rather than continuing automatically.

Use plain UK English. Lead with the learner's outcome, explain the concept, then give supplied steps.
Use A8 text branding. Palette values are provisional, not official brand tokens.
Do not add the internal brand playbook, competitive intelligence, client lists or testimonials to the repo.
