# Getting the course into Databricks with Git

New to Git? You only need three actions for this course: **clone** once, **pull** to get updates and,
occasionally, **discard** your own changes. You never need to commit or push.

## The ideas in one minute

- **GitHub** stores the course files. The copy on GitHub is the master copy.
- **Git** is the tool that copies the files and tracks every change to them.
- A Databricks **Git folder** is your own copy of the course inside your workspace. Databricks knows where it came from,
  so it can fetch updates later.
- **Clone** means making that copy for the first time.
- **Pull** means bringing your copy up to date with GitHub.
- A **local change** is any edit you make to a file in your Git folder, including typing into an exercise cell.
- A **conflict** happens when you pull a file that both you and GitHub have changed. Git cannot decide which
  version wins, so it asks you.

Your **tables, models and saved settings are not in the Git folder**. They live in Unity Catalog and in your workspace
user folder, so you can delete and re-create the Git folder without losing course progress.

## First time: clone the course (5 minutes)

1. In the Databricks left sidebar, click **Workspace**, then open **Users → your email address**.
2. Click **Create → Git folder**.
3. Fill in the dialog:
   - **Git repository URL:** `https://github.com/pdclough-a8/a8-databricks-learning`
   - **Git provider:** GitHub (usually detected automatically)
   - **Git folder name:** leave as `a8-databricks-learning`
   - Leave **Sparse checkout** off.
4. Click **Create Git folder**. After a few seconds you will see `data`, `docs`, `lib`, `notebooks` and other files.
5. Open `notebooks` → `00_setup` and follow it.

The course repository is public, so you do not need a GitHub account to clone or pull it.
If Databricks asks for Git credentials anyway, your workspace requires them for all repositories:
ask your administrator, or use **Settings → Linked accounts** to link GitHub through the browser. Do not create a token
for this course.

## Getting course updates

When you are told the course has been updated:

1. Open any notebook in the course and click the **branch button** (it says `main`) next to the notebook name.
   The Git dialog opens. (From the Workspace browser you can also click **Git** beside the folder name.)
2. Look at the list of **changed files**.
   - **Empty?** Go to step 3.
   - **Files listed?** These are your local edits. If you do not need them, open each file's **⋮** menu and discard
     the change. If you want to keep an answer, copy it somewhere else first.
3. Click **Pull**. The files update to the latest version.
4. Pulling clears any open notebook's state. Start a fresh session: in the compute menu at the top right choose
   **Reset environment** (or detach and reattach), then run the notebook from the top.

**Never commit or push from the course Git folder.** You do not need to, and it could put your edits or
half-resolved files onto the shared course.

## Experiment without causing conflicts

Exercise answers and small experiments are fine in the Git folder if you discard them before the next pull.
For anything you want to keep running, clone the **whole repository into a second Git folder with a different
folder name** and keep your experiments there; do not pull updates into that copy until you have saved your answers.
Keep `notebooks`, `lib` and `data` together. Use the same saved settings to continue with the same course objects,
or a new learner tag and settings profile for a separate set.

**File → Clone** of one notebook outside the Git folder is only a saved record, not a runnable course copy:
the relative `%run ./_config` and repository files will be missing. You can also save just your answer text.

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| A screen titled *Resolve conflict(s) before merge* | You changed a file that the update also changed or deleted | For course files, choose the **incoming** version (**Take all incoming**). If the incoming side says the file was deleted, choose **Keep all current (delete file)**: the course removed it on purpose. Then finish the merge. |
| Lines such as `<<<<<<< Updated upstream`, `=======`, `>>>>>>>` inside a notebook | A conflict was not fully resolved, so Git wrote both versions into the file | Do not run or commit it. In the Git dialog, discard the change to that file and pull again. If that is not offered, use the fix-all route below. |
| Old notebooks that the course no longer lists | A pull kept files you had changed locally | Discard their changes in the Git dialog, or move them to Trash. |
| `FileNotFoundError: [Errno 2] No such file or directory` straight after a pull | Python was still using the folder that the pull replaced | **Reset environment**, then run the notebook from the top. |

**Fix-all route:** right-click the Git folder in Workspace → **Move to Trash**, then clone it again as above.
This loses only edits inside the Git folder. Your tables, models and saved settings remain.

Avoid **Reset** in the Git dialog's **⋮** menu. It also force-pushes to GitHub, which matters if you have
write access to the course repository.

Official reference: [Git operations in Databricks Git folders](https://docs.databricks.com/aws/en/repos/git-operations-with-repos).
