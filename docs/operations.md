# Pause, resume and finish

**Outcome:** stop costs without losing your learning, and delete only what you own when finished.
Keep your exact table/app names and marker in your private progress note.

| State | What to do | What remains |
|---|---|---|
| Pausing after data | Save queries/notebook changes; stop your own compute if permitted | Table and course copy |
| Pausing after a model request | Reset live flags; save verdicts; close Playground | Evidence, no dedicated model resource created by this course |
| Pausing after deployment | Uncheck live; Apps > your app > Stop; verify stopped | App configuration and table |
| Resuming | Verify destination/markers; restart approved compute/app if needed | Same names and learner work, no duplicate creation |
| Finishing permanently | Back up evidence; review and delete exact marked app/table | Course copy/progress unless you remove them separately |

Closing a browser tab does **not** stop compute. A stopped app is **not** a deleted app.
Costs depend on your workspace and billing plan, so confirm stop status and budget with the instructor.
Never stop shared compute without its owner's permission.

## Resume safely

1. Open your own copy, not a fresh clone over learner work.
2. Use the same catalog, schema and tag. Verify table comment and app description.
3. Rerun readiness in the current notebook session. A Python restart loses imported variables.
4. If lesson 1's table exists, reuse it only if marker and fixture match. Do not append or replace.
5. If your app exists, inspect its resources and source. Restart the existing app through Apps if stopped.
   Redeploy only when a source/configuration change requires it.
6. Continue from your last **checked** checkpoint, not the last cell you clicked.

## Final teardown, UI route

These are destructive actions. Do them only when you have finished, not when pausing.

1. Save notebook/query changes and your learning evidence somewhere you intend to keep.
2. Inspect **both** the exact table's comment and app's description before deleting either.
   Both must match `a8-databricks-learning-pilot-v1:YOUR_TAG`. If either differs, stop.
   If one is absent after a partial teardown, check the remaining object.
3. Apps > your exact `a8learn-...-assistant` > Delete. Read and confirm the app name.
   Wait until the app is absent. Do not delete the shared serving endpoint.
4. Catalog Explorer > your exact `a8learn_..._events` > Delete/Drop table.
   Read and confirm the fully qualified name. Never drop the schema or catalog.
5. Remove the manual source-folder read grant if the service principal still exists and the grant is no longer needed.
6. Stop your own notebook compute or SQL warehouse if appropriate. Verify no course app is running.

## Final teardown, code route

Open `notebooks/90_finish`, run setup, and inspect the printed deletion targets.
Only then set `CONFIRM_DELETE` to your exact tag and run the deletion cell.
The helper checks **all existing candidates** before any deletion, then rechecks each marker.
It never creates/deletes a schema, model endpoint or unrelated object.
Reset the confirmation to empty and save the notebook afterwards.

App deletion may be asynchronous. Verify absence in Apps and Catalog Explorer yourself.
Cleanup is not a cross-service transaction: if one deletion fails, preserve the error privately, inspect
the remaining objects and retry with the same tag only after understanding the state.
Missing objects are safe to skip on rerun; permission failures are not interpreted as absence.

Markers guard accidental collisions, not hostile edits or concurrent resource replacement.
Do not share a learner tag. Never use wildcard deletion or change an object's marker to make cleanup pass.
