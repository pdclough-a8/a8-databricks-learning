# A8 | Data to working AI

**Build an assistant you can check, explain and hand over.**

An event operations team needs a quick answer: which events have places left?
You will turn six booking records into checked evidence, give that evidence to a model,
then put the answer behind a small application. One problem, one dataset, one connected journey.

This is **pilot v0.1.0**, not a production system or a promise of business savings.
Our measurable learning outcome is simple: another person can use your app, trace its answer
to the supplied records and understand where it must stop.

## The journey

| Stage | What you do | Evidence you keep |
|---|---|---|
| Strategy | Define the operations question and limits in [readiness](start.md) | Your destination, budget and success criteria |
| Execution, lesson 1 | [Trust the data](lessons/01-data.md) | A checked query and explanation |
| Execution, lesson 2 | [Ask with evidence](lessons/02-model.md) | Three answer verdicts |
| Enablement, lesson 3 | [Put it to work](lessons/03-app.md) | A checked app and short handover |

Allow roughly 20 minutes for readiness and 30–45 minutes per lesson, plus workspace approval
and deployment waits. These are planning estimates, not measured completion times.

## Choose how you work

**UI-led:** Catalog Explorer, the SQL editor, AI Playground and Apps. Copy the supplied short SQL
and prompt blocks. This is low-code, not a claim that a custom Python app can be authored visually.

**Code-first:** supplied Python notebooks inside Databricks. Read the explanation, run the worked
example, make one change, complete a gap, then solve a small transfer task yourself.

Both routes reach the same checkpoints. You can switch at a checkpoint by using the same learner tag,
table and app. Do not recreate objects when switching. The [optional tutor](tutor.md) supports either route.

## Keep the boundaries visible

- All records are synthetic. Never substitute customer, employee or attendee data in this pilot.
- The model receives all six records in its prompt. This is **not RAG**, model training or vector search.
- The app reads the packaged CSV, **not your Unity Catalog table**. Updating that table will not update the app.
  The table teaches governed data and SQL; the fixture keeps application permissions and retrieval out of this first pilot.
- Simulation is deterministic code, **not AI**. It proves the interface, not model quality or authentication.
- Databricks compute, Apps and live inference can incur charges. Nothing here provisions them automatically.
- Live deployment and UI steps still need instructor validation in the target workspace. See [validation](validation.md).

**Start:** [Check readiness](start.md). **When stopping:** [pause or finish](operations.md).
