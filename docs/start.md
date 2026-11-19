# Get ready, without surprises

**Outcome:** you know where you are working, what may bill and what success looks like.
Do this once before lesson 1. You need a browser, not a local development environment.

## 1. Agree the workspace and budget

Ask your instructor or administrator for the following. Do not guess a catalog or use a personal
author's workspace settings.

| Need | Why |
|---|---|
| An authorised Databricks workspace with Unity Catalog | Stores the lesson table |
| An existing writable catalog and schema | No new schema is created in this course |
| `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`, and access to your own table | Read/create the learning fixture |
| Python notebook compute; SQL warehouse for the UI SQL route | Executes lesson 1; starting compute may bill |
| AI Playground and an approved chat-completions serving endpoint, with query permission | Optional live lesson 2 |
| Apps creation/deployment permission and available app compute | Lesson 3, even simulation may bill |
| Ability to add a model resource and grant the app identity source-folder read access | App workload authentication |
| A spending limit, stop rules and an owner for problems | Prevents unattended cost |

Some workspaces or editions do not support all of these. **Free Edition is not assumed to support the
whole course.** If Apps or model access is unavailable, complete the supported stages and mark the
blocked checkpoint honestly. Simulation is not a substitute for a live-model pass.

The pilot uses an existing **serving endpoint** through the SDK chat client and Apps Model resource.
Current Databricks guidance also offers newer gateway/model-service paths. If your organisation permits
only that path, stop and have the instructor adapt and validate the integration before teaching.
Do not create a legacy endpoint or a PAT just to follow this pilot.

## 2. Open a full personal course copy

GitHub is the intended source of truth once a maintainer publishes an approved release.
**This local pilot has no published repository URL yet.** The maintainer must supply the real URL and release
before asking learners to clone it. Do not paste a placeholder URL into Databricks.

When supplied, in Workspace choose **Create > Git folder**, paste the course repository URL, choose the
approved release branch/tag supported by your workspace and create it in your personal area.
If your Git folder UI cannot select the release tag, use the instructor's release branch or exact release archive.
Public clones may not need credentials; private access and pushing changes require the workspace's Git
authentication flow. Use browser OAuth, never create a long-lived token for this course.

For this unpublished pilot, the instructor can supply a full archive of this repository, excluding `.git`,
`.packages`, caches and secrets. Extract it, then use Workspace's upload/import controls to upload the complete
folder tree into your personal area. Confirm both notebooks and ordinary files are present. Importing just
one `.py` notebook is not enough. If the UI cannot preserve the tree, stop and ask for a prepared course folder.

You must see:

```text
notebooks/00_start_here
notebooks/01_explore_events
notebooks/02_ask_a_model
notebooks/03_deploy_assistant
notebooks/90_finish
course/workspace_ops.py
app/event_assistant/app.py
app/event_assistant/logic.py
app/event_assistant/data/events.csv
```

The notebook sources use Databricks `.py` headers and cell delimiters. Open them as notebooks,
not plain Python files. Keep the app and helper modules as ordinary files.

## 3. Reserve your names

Choose a unique tag, for example `learner07`, assigned per learner and workspace.
Use lowercase letters, digits and underscores, start with a letter, maximum 16 characters.
Catalog/schema identifiers in this pilot use the same syntax, maximum 48 characters.
Names containing spaces or hyphens require an instructor adaptation; don't silently change a real name.

| Object | Name |
|---|---|
| Table | `YOUR_CATALOG.YOUR_SCHEMA.a8learn_YOUR_TAG_events` |
| App | `a8learn-YOUR-TAG-assistant` (tag underscores become hyphens) |
| Table comment / app description | `a8-databricks-learning-pilot-v1:YOUR_TAG` |

Replace every uppercase placeholder before using it. The tag must also distinguish concurrent learners.
Never write to `system`, `samples` or `dbacademy`. The marker is collision protection, not proof of security ownership.
If an object already exists without your exact marker, **stop**, do not adopt it by changing its marker.

=== "UI-led"

    1. Open Catalog Explorer and locate your assigned catalog/schema. Confirm you recognise it.
    2. Check your intended table name does not exist. Check the intended app name under Apps.
    3. Copy your exact names and marker into a private [progress note](progress.md).
    4. Download the six-row `events.csv` from the supplied course package for lesson 1.
    5. Check your SQL warehouse and Playground endpoint with the instructor. Do not send a model request yet.

=== "Code-first"

    1. Open `notebooks/00_start_here` in your personal course folder.
    2. Attach approved Python compute. The notebook itself needs no package installation.
    3. Run the widget-creation cell. Fill catalog, schema, learner_tag and, if approved, serving_endpoint.
    4. Run the configuration cell, not Run All. It reads schema metadata and displays your names.
    5. Confirm the six synthetic records. A successful metadata read does **not** prove write rights.
    6. Later notebooks use `%run ./00_start_here`. Supply the same widget values in each notebook;
       do not assume another notebook's widgets carry across.

## 4. Write a success statement

In your progress note complete: "The operations team can identify ___ from ___, but must not use this
assistant to ___." A useful answer is availability from the six supplied records, not forecasts or bookings.

**Readiness checkpoint:** you can identify the destination, possible costs, data limits and stop procedure.
Continue to [lesson 1](lessons/01-data.md).
