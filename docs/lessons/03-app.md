# 3. Put it to work

**Outcome:** someone else can use your supplied app and understand its limits.
Start with your lesson 2 verdicts, approved Apps access and an authorised serving endpoint.
Finish with a checked deployment and a short handover, not just a green deployment status.

## Understand the move

The notebook ran as you. A deployed Databricks App runs its model requests as an **app service
principal**, a separate workload identity with its own permissions. A Model resource grants that
identity permission to query the selected endpoint; it does not grant table access.

This app ships the same six-row CSV inside its folder and sends the records in full.
It **does not query the lesson 1 table**, search documents or change bookings.
That deliberate simplification isolates the first application and identity lessons.
A future path can replace the fixture with an authorised query and teach that dependency explicitly.

The interface is supplied Streamlit Python. The UI route configures and deploys it; it is not
no-code app authorship. Deployment starts compute that may bill, even with simulation selected.

## Create and deploy

=== "UI-led"

    1. In **Compute > Apps** (or **Apps** in your navigation), check your intended name is absent.
       Choose **Create app**, using the custom/your-own-code path, not a template that auto-deploys.
       Enter `a8learn-YOUR-TAG-assistant` and your exact ownership marker as the description.
       If your UI cannot set the description at creation, set it on your newly created app before proceeding.
    2. Add a resource of type **Model / Serving endpoint**. Select the approved endpoint,
       choose **Can query**, and use resource key **`model`**. Do not request manage permission.
    3. Complete app creation. Wait for app compute to be ready. Note its service principal in app details.
    4. In Workspace, open the permissions menu of **only** your `app/event_assistant` source folder.
       Grant that app service principal **Can read**. Do not grant it the whole user folder or repository.
       If your workspace needs a different source-access mechanism, ask the administrator to validate it.
    5. In app overview choose **Deploy > From workspace**. Select the full workspace folder ending
       `/app/event_assistant`, not the repository root. It must include `app.py`, `logic.py`, `style.css`,
       `.streamlit/config.toml`, `requirements.txt`, `app.yaml` and `data/events.csv`.
    6. Review the selected path and resource, then deploy. Inspect deployment status and logs.
       Python dependencies install from `requirements.txt`; `app.yaml` supplies the Streamlit command.
       Never paste credentials into a file or a deployment field.

=== "Code-first"

    1. Open `notebooks/03_deploy_assistant`. Run the dependency preparation cells, then setup with your usual widgets.
    2. Inspect APP_NAME, MARKER and source path. Enable `CREATE_MY_APP`, run once, then reset it to `False`.
       Creation may start billable app compute. The helper sends the Apps API a model resource with Can query.
    3. Open the created app in the UI. Wait for compute readiness; inspect its description and model resource.
       If it already existed with your marker, the code reused it without reconfiguration. Confirm its resource
       is still key `model` pointing to the intended endpoint.
    4. Grant its service principal Can read on only `app/event_assistant`, as in UI steps 3–4.
       This permission grant is intentionally manual.
    5. Confirm SOURCE_PATH starts `/Workspace/` and ends `/app/event_assistant`.
       Enable `DEPLOY_MY_APP`, run once, then reset it to `False`.
    6. Open app overview and inspect deployment status/logs. An accepted API request is not a running app.

If policy allows only Git-source app deployment, stop here. This pilot's runnable route uses a workspace
snapshot and needs instructor adaptation for that policy. Do not weaken organisation controls.
Deployment snapshots are separate from later source edits: redeploy to publish a change.

## Check the supplied example

Open the app URL from app overview. Keep access private to the approved learners.

1. Confirm **Use a live model (billable)** is off.
2. Run "Which events are in Leeds?" Expect **Simulation, not AI**, E101=18 and E104=22.
3. Change the question to "What is the cancellation policy?" Expect an explicit unsupported-simulation
   response. No AI quality claim can be made from this test.
4. With approval, select live mode and send the Leeds question once. Then, within your agreed budget,
   test Manchester under ten and missing policy using lesson 2's rubric. Check the app identity's
   resource access, not just whether your user can query the endpoint.
5. Uncheck live mode. Keep your factual verdicts and deployment status in your progress note.
   UI reruns and checkbox changes do not send a request; only submitting the form does.

## Make one change, complete a gap, transfer

**Change:** open your `app.py` source and change `APP_TITLE` to `A8 | Event Team Assistant`.
Redeploy, refresh the app and confirm the visible title changed. Restore the original title and redeploy again.
Even on the UI route, this small text edit is Python source editing.

**Complete:** "The notebook model call runs as ___; the deployed model call runs as ___."
Answer: your user; the app service principal. A visitor's permissions are not automatically delegated.

**Transfer:** give another approved learner a four-sentence handover without copying this page.
State what the app helps with, where the evidence comes from, what it cannot do and how to stop it.
Ask them to identify one claim they would reject. Do not share app access more widely without permission.

**Checkpoint:** a deployment plus tested behaviour plus an explanation.
If only simulation passed, record **interface checked, live access/quality not checked**.
Go to [pause or finish](../operations.md), then complete [your evidence record](../progress.md).

## Diagnose without guessing

| Symptom | Check first |
|---|---|
| Source path rejected | Exact app subfolder, source read grant and workspace-source policy |
| Model resource missing | Key `model` matches `app.yaml`'s `valueFrom`; redeploy after configuration changes |
| Notebook works, app fails | App service principal's endpoint permission, not your personal grants |
| Empty answer | Chat-compatible endpoint and output budget/parameter compatibility |
| Source edit not visible | Correct workspace path, fresh deployment, refreshed browser |
| Table edit not visible | Expected: this pilot app uses its packaged CSV |

The app intentionally gives a sanitised error rather than exposing raw provider exceptions.
Review logs privately with the instructor. Never send raw logs or secrets to a tutor.
