"""Maintainer-only, explicitly authorised a8-free validation of Modules 8a-13 and the Python routes. Not a unit test.

Run with Python and the Databricks SDK installed, using the browser OAuth profile a8-free. Uploads the course to a
unique, non-Git workspace folder, runs 00, 01, 03, 04, 05, 08a, 08b, 08c, 09, 12 and 13 as serverless notebook
tasks under its own learner tag and saved-settings profile, then always runs scoped cleanup, deletes the uploaded
folder and its settings file, and writes the notebook outputs to .local-validation/stage2-validation.txt (git-ignored).

Model requests and a billable Vector Search endpoint are approved by whoever runs this, with --approve-cloud-writes.
"""
import argparse
import base64
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import NotebookTask, RunIf, SubmitTask, TaskDependency, ViewsToExport
from databricks.sdk.service.workspace import ImportFormat, Language

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "val8cfg"


def upload(w, remote):
    w.workspace.mkdirs(remote)
    for folder in ["lib", "data/raw", "data/docs", "dashboards", "notebooks", "pipelines", "app"]:
        for source in (ROOT / folder).rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            target = f"{remote}/{source.relative_to(ROOT).as_posix()}"
            notebook = folder in {"notebooks", "pipelines"}
            sql = source.suffix == ".sql"
            if notebook:
                target = target.removesuffix(".py").removesuffix(".sql")
            w.workspace.mkdirs(target.rsplit("/", 1)[0])
            language = (Language.SQL if sql else Language.PYTHON) if notebook else None
            w.workspace.upload(target, source.read_bytes(),
                               format=ImportFormat.SOURCE if notebook else ImportFormat.RAW,
                               language=language, overwrite=False)


def build_tasks(remote, tag, wait_minutes, skip_vector=False, only=None):
    common = {"config_profile": PROFILE, "answers": "solutions"}
    plan = [
        ("setup", "00_setup",
         {"catalog": "workspace", "schema": "default", "tag": tag, "run_write_probe": "yes"}, 1800),
        ("data", "01_lakehouse_data", {}, 2400),
        ("descriptive", "03_descriptive_analytics", {"create_reporting_view": "yes"}, 1800),
        ("diagnostic", "04_diagnostic_analytics", {}, 1800),
        ("predictive", "05_predictive_ml", {"deploy_serving": "no"}, 2400),
        ("embeddings", "08a_embeddings", {"embed_comments": "yes", "embed_python": "yes"}, 1800),
        ("rag", "08b_rag", {"embed_chunks": "yes", "ask_model": "yes"}, 1800),
        ("vector", "08c_vector_search", {"create_vs_endpoint": "yes", "create_vs_index": "yes", "ask_model_vs": "yes",
                                         "delete_vector_search": "yes", "wait_minutes": str(wait_minutes)},
         wait_minutes * 60 * 2 + 1800),
        ("agents", "09_agents", {"ask_agent": "yes", "native_tools": "yes"}, 1800),
        ("deploy", "12_deploy_and_govern",
         {"register_agent": "yes", "deploy_agent": "yes", "delete_agent_endpoint": "yes"}, 3000),
        ("pipelines", "13_pipelines_and_jobs",
         {"create_pipeline": "yes", "run_pipeline": "yes", "run_job": "yes", "delete_pipeline_objects": "yes"}, 3600),
        ("app", "11_interactive_app",
         {"create_app": "yes", "grant_app_access": "yes", "deploy_app": "yes", "delete_app": "yes"}, 2400),
        ("evaluate", "14_evaluate_and_monitor",
         {"run_evaluation": "yes", "run_judge": "yes", "evaluate_endpoint": "no"}, 2400),
        # Needs a Champion from the deploy task. The canary stays off until a write probe has proved traffic splits.
        ("release", "15_release_and_rollback",
         {"log_candidates": "yes", "release_candidate": "yes", "roll_back": "yes", "canary_endpoint": "no"}, 2400),
    ]
    tasks = []
    for key, notebook, extra, timeout in plan:
        if (skip_vector and key == "vector") or (only and key not in only):
            continue
        tasks.append(SubmitTask(
            task_key=key,
            notebook_task=NotebookTask(notebook_path=f"{remote}/notebooks/{notebook}",
                                       base_parameters={**common, **extra}),
            depends_on=[TaskDependency(task_key=tasks[-1].task_key)] if tasks else None,
            run_if=RunIf.ALL_DONE if tasks and key != "data" else None, timeout_seconds=timeout))
    for key, previous in [("cleanup", tasks[-1].task_key), ("cleanup_again", "cleanup")]:
        tasks.append(SubmitTask(
            task_key=key,
            notebook_task=NotebookTask(
                notebook_path=f"{remote}/notebooks/99_pause_and_cleanup",
                base_parameters={"config_profile": PROFILE, "cleanup_action": "all_course_objects",
                                 "confirm_tag": tag}),
            depends_on=[TaskDependency(task_key=previous)], run_if=RunIf.ALL_DONE, timeout_seconds=1800))
    return tasks


def notebook_text(w, run_id):
    """Plain text of each cell's output, taken from the exported run page."""
    try:
        views = w.jobs.export_run(run_id=run_id, views_to_export=ViewsToExport.ALL).views or []
    except Exception as error:  # export is best effort; the task state is the primary record
        return f"(export failed: {error})"
    lines = []
    for view in views:
        match = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", view.content or "")
        if not match:
            continue
        model = json.loads(urllib.parse.unquote(base64.b64decode(match.group(1)).decode("utf-8")))
        for command in model.get("commands", []):
            results = command.get("results") or {}
            data = results.get("data")
            text = data if isinstance(data, str) else json.dumps(data)[:1500] if data else ""
            summary = results.get("summary") or results.get("cause") or ""
            if text or summary:
                lines.append(f"--- {command.get('command', '')[:90].splitlines()[0] if command.get('command') else ''}")
                lines.append(str(text)[:2500])
                if summary:
                    lines.append(f"[error] {str(summary)[:1500]}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-cloud-writes", action="store_true", required=True)
    parser.add_argument("--tag", default="val8")
    parser.add_argument("--wait-minutes", type=int, default=25)
    parser.add_argument("--only", help="comma-separated task keys to run, in the usual order")
    parser.add_argument("--skip-vector", action="store_true", help="do not create the billable Vector Search endpoint")
    args = parser.parse_args()
    w = WorkspaceClient(profile="a8-free")
    user = w.current_user.me().user_name
    remote = f"/Users/{user}/a8learn_stage2_validation_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    upload(w, remote)
    run_id = w.jobs.submit(run_name="A8 Stage 2 notebook validation",
                           tasks=build_tasks(remote, args.tag, args.wait_minutes, args.skip_vector,
                                              set(args.only.split(",")) if args.only else None)).run_id
    print(json.dumps({"run_id": run_id, "folder": remote, "tag": args.tag}), flush=True)
    while True:
        run = w.jobs.get_run(run_id)
        state = run.state.life_cycle_state.value if run.state and run.state.life_cycle_state else "?"
        print(datetime.now(timezone.utc).strftime("%H:%M:%S"), state,
              {t.task_key: (t.state.result_state.value if t.state and t.state.result_state else
                            t.state.life_cycle_state.value if t.state and t.state.life_cycle_state else "?")
               for t in run.tasks or []}, flush=True)
        if state in {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}:
            break
        time.sleep(60)
    report = Path(ROOT / ".local-validation" / "stage2-validation.txt")
    report.parent.mkdir(exist_ok=True)
    with report.open("w", encoding="utf-8") as out:
        for task in run.tasks or []:
            result = task.state.result_state.value if task.state and task.state.result_state else "?"
            message = task.state.state_message if task.state else ""
            out.write(f"\n===== {task.task_key}: {result} {message}\n")
            out.write(notebook_text(w, task.run_id) + "\n")
            if result != "SUCCESS":
                try:
                    detail = w.jobs.get_run_output(task.run_id)
                    out.write(f"[error] {detail.error}\n{(detail.error_trace or '')[:3000]}\n")
                except Exception as error:
                    out.write(f"[no run output: {error}]\n")
    w.workspace.delete(remote, recursive=True)
    try:
        w.workspace.delete(f"/Users/{user}/a8learn/{PROFILE}.json")
    except Exception:
        pass
    print("Report:", report, flush=True)


if __name__ == "__main__":
    main()
