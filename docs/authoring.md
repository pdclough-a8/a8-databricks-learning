# Add an application path, not a framework

**Outcome:** a maintainer can extend the course without making learners repeat the foundations.
Reuse readiness, namespace safety, evidence checking, identity, operations and the tutor contract.
Add a new application folder only when its learning purpose is clear.

## Path template

```text
Application name and intended user:
Business decision or task:
Observable success, and explicit non-goals:
Shared foundations required:
New concepts, and why each is needed:
Synthetic evidence fixture and source of expected answers:
UI-led route (honest low-code boundaries):
Code-first notebooks:
Worked example:
One-change exercise:
Gap-completion task, hint and full solution:
Independent transfer task:
Functional checks and explanation prompts:
Identity, permissions, approved costs:
Pause/resume state and final teardown:
Offline tests:
Live acceptance matrix and validation owner:
```

The next meaningful extension could replace the CSV with a scoped Unity Catalog query, then add retrieval
and evaluate evidence selection separately from generation. Don't call today's full-record prompt RAG.
Do not add vector search, agents, training or production bundles merely to cover product features.
Git folders are the learning surface; deployment engineering and bundles belong in a later path.

## Release without losing work

Keep source in GitHub once publishing is authorised. Release the site, app, notebooks and fixtures together
under a versioned tag; record the supported workspace/compute/API path and validation date.
Give learners a release branch or archive their Git-folder UI can actually open.
Never tell a learner to reset or pull over their exercises. Keep a personal branch/copy and migrate changes explicitly.
Use a fresh test learner/tag for instructor acceptance, never someone's in-progress objects.

Before teaching, run both routes from a fresh copy, switch routes at a checkpoint,
pause/restart, retry after partial work and test final cleanup. See the [validation ledger](validation.md).
Before publishing, get brand approval and remove private learner evidence. Publishing is a separate decision.

## Why the lesson pattern looks this way

Outcomes, practice and checks are aligned rather than a list of platform clicks:
[CMU, alignment](https://www.cmu.edu/teaching/assessment/basics/alignment.html).
Worked examples and gradually reduced support manage cognitive load:
[NSW, cognitive load in practice](https://education.nsw.gov.au/about-us/education-data-and-research/cese/publications/practical-guides-for-educators/cognitive-load-theory-in-practice).
Revisiting and recalling explanations supports retention:
[IES, organising instruction and study](https://ies.ed.gov/ncee/wwc/PracticeGuide/1).
These inform the design; they are not evidence that this pilot has already improved learning outcomes.
