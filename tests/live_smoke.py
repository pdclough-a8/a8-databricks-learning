"""Maintainer-only, explicitly authorised a8-free smoke run. Never imported by unit tests.

Run with Python 3.12 and Databricks SDK installed. Uses browser OAuth profile a8-free.
Uploads only course notebooks/lib/data to a unique, non-Git test folder.
Always schedules scoped cleanup, even after failed teaching tasks.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat, Language
from databricks.sdk.service.jobs import SubmitTask, NotebookTask, TaskDependency, RunIf

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-cloud-writes", action="store_true", required=True)
    parser.add_argument("--tag", default="smoke")
    args = parser.parse_args()
    w = WorkspaceClient(profile="a8-free")
    user = w.current_user.me().user_name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    remote = f"/Users/{user}/a8learn_stage1_smoke_{stamp}"
    w.workspace.mkdirs(remote)
    for folder in ["lib", "data/raw", "notebooks", "tests"]:
        for source in (ROOT / folder).rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            if folder == "tests" and source.name != "acceptance_notebook.py":
                continue
            relative = source.relative_to(ROOT).as_posix()
            target = f"{remote}/{relative}"
            notebook = folder in {"notebooks", "tests"}
            if notebook:
                target = target.removesuffix(".py")
            w.workspace.mkdirs(target.rsplit("/", 1)[0])
            w.workspace.upload(
                target, source.read_bytes(), format=ImportFormat.SOURCE if notebook else ImportFormat.RAW,
                language=Language.PYTHON if notebook else None, overwrite=False,
            )
    params = {"config_profile": "stage1_smoke", "answers": "solutions"}
    tasks = []
    for key, notebook, extra in [
        ("setup", "00_setup", {"catalog": "workspace", "schema": "default", "tag": args.tag, "run_write_probe": "yes"}),
        ("data", "01_lakehouse_data", {}),
        ("governance", "02_governance", {"read_system_evidence": "yes"}),
        ("ml", "03_predictive_ml", {"deploy_serving": "yes"}),
    ]:
        tasks.append(SubmitTask(
            task_key=key, notebook_task=NotebookTask(
                notebook_path=f"{remote}/notebooks/{notebook}", base_parameters={**params, **extra}),
            depends_on=[TaskDependency(task_key=tasks[-1].task_key)] if tasks else None,
            timeout_seconds=2400,
        ))
    # Retrain without serving: proves append history and latest-per-booking forecasts on existing objects.
    tasks.append(SubmitTask(
        task_key="ml_again",
        notebook_task=NotebookTask(
            notebook_path=f"{remote}/notebooks/03_predictive_ml",
            base_parameters={**params, "deploy_serving": "no"},
        ),
        depends_on=[TaskDependency(task_key="ml")], timeout_seconds=2400,
    ))
    tasks.append(SubmitTask(
        task_key="acceptance",
        notebook_task=NotebookTask(notebook_path=f"{remote}/tests/acceptance_notebook"),
        depends_on=[TaskDependency(task_key="ml_again")], timeout_seconds=900,
    ))
    for key, previous in [("cleanup", "acceptance"), ("cleanup_again", "cleanup")]:
        tasks.append(SubmitTask(
            task_key=key,
            notebook_task=NotebookTask(
                notebook_path=f"{remote}/notebooks/99_pause_and_cleanup",
                base_parameters={"config_profile": "stage1_smoke",
                                 "cleanup_action": "all_course_objects", "confirm_tag": args.tag}),
            depends_on=[TaskDependency(task_key=previous)], run_if=RunIf.ALL_DONE, timeout_seconds=1200,
        ))
    run = w.jobs.submit(run_name="A8 Stage 1 notebook smoke", tasks=tasks).run_id
    print(json.dumps({"run_id": run, "folder": remote, "profile": "a8-free", "tag": args.tag}), flush=True)


if __name__ == "__main__":
    main()
