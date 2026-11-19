"""Explicitly called cloud operations, never run on import.

Marker checks prevent accidental collisions, not hostile concurrent edits.
No schema, endpoint, permission grant or shared resource is created here.
"""

import re
import uuid

from logic import names, ownership_marker, require_owner


def table_marker(spark, table):
    details = spark.sql(f"DESCRIBE TABLE EXTENDED {table}").collect()
    return next((r["data_type"] for r in details if r["col_name"] == "Comment"), None)


def check_table(spark, catalog, schema, tag, rows):
    table, _ = names(catalog, schema, tag)
    if not spark.catalog.tableExists(table):
        return False
    require_owner(table_marker(spark, table), tag)
    actual = [r.asDict() for r in spark.table(table).collect()]
    if sorted(actual, key=lambda r: r["event_id"]) != sorted(rows, key=lambda r: r["event_id"]):
        raise ValueError("Existing table differs from the fixture. Preserve it and ask your instructor.")
    return True


def ensure_table(spark, catalog, schema, tag, rows):
    table, _ = names(catalog, schema, tag)
    if check_table(spark, catalog, schema, tag, rows):
        return table
    view = f"a8_fixture_{uuid.uuid4().hex}"
    spark.createDataFrame(
        rows, "event_id string, event_name string, city string, capacity long, booked long",
    ).createOrReplaceTempView(view)
    try:
        # One Delta CTAS commit: no marked-but-empty intermediate table, no append on rerun.
        spark.sql(
            f"CREATE TABLE {table} USING DELTA COMMENT '{ownership_marker(tag)}' "
            f"AS SELECT event_id, event_name, city, capacity, booked FROM {view}"
        )
    finally:
        spark.catalog.dropTempView(view)
    check_table(spark, catalog, schema, tag, rows)
    return table


def get_app(workspace, app_name):
    from databricks.sdk.errors import NotFound

    try:
        return workspace.api_client.do("GET", f"/api/2.0/apps/{app_name}")
    except NotFound:
        return None


def ensure_app(workspace, catalog, schema, tag, endpoint):
    _, app_name = names(catalog, schema, tag)
    if not isinstance(endpoint, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", endpoint):
        raise ValueError("Supply an authorised serving endpoint name, not a URL.")
    current = get_app(workspace, app_name)
    if current is not None:
        require_owner(current.get("description"), tag)
        return current
    return workspace.api_client.do("POST", "/api/2.0/apps", body={
        "name": app_name,
        "description": ownership_marker(tag),
        "resources": [{"name": "model", "serving_endpoint": {
            "name": endpoint, "permission": "CAN_QUERY",
        }}],
    })


def deploy_app(workspace, catalog, schema, tag, source_path):
    _, app_name = names(catalog, schema, tag)
    if not isinstance(source_path, str) or not source_path.startswith("/Workspace/"):
        raise ValueError("Use the full /Workspace/.../app/event_assistant source folder.")
    if not source_path.endswith("/app/event_assistant") or any(
        part in {".", "..", ""} for part in source_path.split("/")[1:]
    ):
        raise ValueError("Deploy only this course's app/event_assistant folder.")
    current = get_app(workspace, app_name)
    if current is None:
        raise ValueError("Create your marked app first.")
    require_owner(current.get("description"), tag)
    return workspace.api_client.do("POST", f"/api/2.0/apps/{app_name}/deployments", body={
        "source_code_path": source_path, "mode": "SNAPSHOT",
    })


def cleanup(workspace, spark, catalog, schema, tag, confirmation):
    table, app_name = names(catalog, schema, tag)
    if confirmation != tag:
        raise ValueError("Nothing deleted. Type your exact learner tag to confirm final deletion.")
    # Preflight all candidates before any deletion. Permission failures are not treated as absence.
    has_table = spark.catalog.tableExists(table)
    if has_table:
        require_owner(table_marker(spark, table), tag)
    app = get_app(workspace, app_name)
    if app is not None:
        require_owner(app.get("description"), tag)
    if app is not None:
        require_owner(get_app(workspace, app_name).get("description"), tag)
        workspace.api_client.do("DELETE", f"/api/2.0/apps/{app_name}")
    if has_table:
        require_owner(table_marker(spark, table), tag)
        spark.sql(f"DROP TABLE {table}")
    return {"table": table, "app": app_name, "app_deletion_requested": app is not None}
