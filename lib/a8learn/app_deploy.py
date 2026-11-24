"""Module 11: the learner's own Databricks App. Source is generated per learner; cleanup is scoped by exact name."""

from . import COURSE_ID, quote


def app_yaml(course, warehouse_resource="warehouse", availability_key="event_availability"):
    """The app.yaml written next to app.py: the command, and the two settings the app reads."""
    return (
        'command: ["streamlit", "run", "app.py"]\n'
        "env:\n"
        "  - name: A8_WAREHOUSE_ID\n"
        f"    valueFrom: {warehouse_resource}\n"
        "  - name: A8_VIEW\n"
        f'    value: "{course.t(availability_key)}"\n'
    )


def app_description(course):
    """The course marker stored in the app description; cleanup refuses an app without it."""
    return f"{COURSE_ID} {course.cfg.tag} seats-left app"


def app_for_cleanup(course, workspace):
    """The learner's own app by exact name, creator and course marker, or None."""
    from databricks.sdk.errors import NotFound
    try:
        app = workspace.apps.get(course.app_name)
    except NotFound:
        return None
    if app.creator != course.cfg.user or (app.description or "") != app_description(course):
        raise PermissionError("App creator or course marker does not match. Nothing deleted.")
    return app


def revoke_app_grants(course, workspace, app):
    """Revoke what Module 11 granted to the app's service principal. A missing grant is not an error."""
    principal = f"`{app.service_principal_client_id}`"
    # Either source may have been granted by an earlier deployment.
    for key, kind in (("event_availability", "VIEW"), ("seats_live", "TABLE")):
        if course.exists(key):
            course.spark.sql(f"REVOKE SELECT ON {kind} {course.t(key)} FROM {principal}")
    for statement in (f"REVOKE USE SCHEMA ON SCHEMA {course.schema_fqn} FROM {principal}",
                      f"REVOKE USE CATALOG ON CATALOG {quote(course.cfg.catalog)} FROM {principal}"):
        course.spark.sql(statement)


def delete_app(course, workspace):
    """Revoke grants, delete the app and its source folder. Returns True if an app was removed."""
    from databricks.sdk.errors import NotFound
    app = app_for_cleanup(course, workspace)
    if app is not None:
        revoke_app_grants(course, workspace, app)
        workspace.apps.delete(course.app_name)
    try:
        workspace.workspace.delete(course.app_folder, recursive=True)
    except NotFound:
        pass
    return app is not None

