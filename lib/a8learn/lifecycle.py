"""Exact-name, owner/marker checked teardown; no list-and-prefix deletion."""

import time

from . import COURSE_ID, OBJECTS
from .app_deploy import app_for_cleanup, delete_app


def endpoint_for_cleanup(course, workspace, name=None):
    from databricks.sdk.errors import NotFound
    name = name or course.endpoint_name
    try:
        endpoint = workspace.serving_endpoints.get(name)
    except NotFound:
        return None
    tags = {t.key: t.value for t in endpoint.tags or []}
    if (endpoint.creator != course.cfg.user or tags.get("a8learn_course") != COURSE_ID
            or tags.get("a8learn_tag") != course.cfg.tag):
        raise PermissionError("Endpoint owner/course tags do not match. Nothing deleted.")
    return endpoint


def vector_search_for_cleanup(course, workspace):
    """This learner's Vector Search index and endpoint (each may be None). Refuses anything not theirs."""
    from databricks.sdk.errors import NotFound
    index = endpoint = None
    try:
        index = workspace.vector_search_indexes.get_index(course.vector_index_name)
    except NotFound:
        pass
    try:
        endpoint = workspace.vector_search_endpoints.get_endpoint(course.vector_endpoint_name)
    except NotFound:
        pass
    if index is not None and (index.creator != course.cfg.user or index.endpoint_name != course.vector_endpoint_name):
        raise PermissionError("Vector Search index creator or endpoint does not match. Nothing deleted.")
    if endpoint is not None:
        if endpoint.creator != course.cfg.user:
            raise PermissionError("Vector Search endpoint creator does not match. Nothing deleted.")
        if (endpoint.num_indexes or 0) > (1 if index is not None else 0):
            raise PermissionError("The endpoint hosts other indexes. Nothing deleted.")
    return index, endpoint


def delete_vector_search(course, workspace, index, endpoint, wait_seconds=180):
    """Delete the index first (an endpoint cannot be removed while it hosts one), then the endpoint."""
    from databricks.sdk.errors import NotFound
    if index is not None:
        workspace.vector_search_indexes.delete_index(course.vector_index_name)
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            try:
                workspace.vector_search_indexes.get_index(course.vector_index_name)
            except NotFound:
                break
            time.sleep(5)
    if endpoint is not None:
        workspace.vector_search_endpoints.delete_endpoint(course.vector_endpoint_name)


def pipeline_for_cleanup(course, workspace):
    """The learner's own bookings pipeline (Module 13) by exact name, creator and course marker, or None."""
    found = [p for p in workspace.pipelines.list_pipelines(filter=f"name LIKE '{course.pipeline_name}'")
             if p.name == course.pipeline_name]
    if not found:
        return None
    info = workspace.pipelines.get(found[0].pipeline_id)
    configuration = (info.spec.configuration if info.spec else None) or {}
    if (info.creator_user_name != course.cfg.user or configuration.get("a8learn_course") != COURSE_ID
            or configuration.get("a8learn_tag") != course.cfg.tag):
        raise PermissionError("Pipeline creator/course settings do not match. Nothing deleted.")
    return info


def job_for_cleanup(course, workspace):
    """The learner's own refresh job (Module 13) by exact name, creator and course tags, or None."""
    found = [j for j in workspace.jobs.list(name=course.job_name) if j.settings and j.settings.name == course.job_name]
    if not found:
        return None
    job = found[0]
    tags = job.settings.tags or {}
    if (job.creator_user_name != course.cfg.user or tags.get("a8learn_course") != COURSE_ID
            or tags.get("a8learn_tag") != course.cfg.tag):
        raise PermissionError("Job creator/course tags do not match. Nothing deleted.")
    return job


def model_for_cleanup(course, workspace, client, name=None):
    import mlflow
    name = name or course.model_name
    try:
        model = client.get_registered_model(name)
    except mlflow.exceptions.MlflowException as error:
        if error.error_code == "RESOURCE_DOES_NOT_EXIST":
            return None
        raise
    if (model.tags.get("a8learn_course") != COURSE_ID or
            model.tags.get("a8learn_tag") != course.cfg.tag or
            workspace.registered_models.get(name).owner != course.cfg.user):
        raise PermissionError("Model ownership/course tags do not match. Nothing deleted.")
    return model


def cleanup(course, workspace, client, confirmation, tables=False):
    """Delete endpoint, optionally tables/model/experiment. Config and source files stay."""
    if confirmation != course.cfg.tag:
        raise ValueError("Type your exact learner tag to confirm deletion.")
    endpoint = endpoint_for_cleanup(course, workspace)
    agent_endpoint = endpoint_for_cleanup(course, workspace, course.agent_endpoint_name)
    index, vector_endpoint = vector_search_for_cleanup(course, workspace)
    pipeline = pipeline_for_cleanup(course, workspace)
    job = job_for_cleanup(course, workspace)
    app = app_for_cleanup(course, workspace)
    keys = [k for k in reversed(OBJECTS) if OBJECTS[k][0] != "model"] if tables else []
    present = [k for k in keys if course.exists(k)]
    # Preflight every intended target before the first delete.
    for key in present:
        course.guard(key)
    model = model_for_cleanup(course, workspace, client) if tables else None
    agent_model = model_for_cleanup(course, workspace, client, course.agent_model_name) if tables else None
    experiment = client.get_experiment_by_name(course.experiment_path) if tables else None
    if experiment and (experiment.tags.get("a8learn_course") != COURSE_ID or
                       experiment.tags.get("a8learn_tag") != course.cfg.tag):
        raise PermissionError("Experiment has no matching course tags. Nothing deleted.")
    if endpoint:
        endpoint_for_cleanup(course, workspace)
        workspace.serving_endpoints.delete(course.endpoint_name)
    if app:
        delete_app(course, workspace)
    if job:  # the job runs the pipeline, so it goes first
        job_for_cleanup(course, workspace)
        workspace.jobs.delete(job.job_id)
    if pipeline:
        pipeline_for_cleanup(course, workspace)
        workspace.pipelines.delete(pipeline.pipeline_id)
    if agent_endpoint:
        endpoint_for_cleanup(course, workspace, course.agent_endpoint_name)
        workspace.serving_endpoints.delete(course.agent_endpoint_name)
    if index is not None or vector_endpoint is not None:
        vector_search_for_cleanup(course, workspace)
        delete_vector_search(course, workspace, index, vector_endpoint)
    if tables:
        for found, name in ((agent_model, course.agent_model_name), (model, course.model_name)):
            if found:
                model_for_cleanup(course, workspace, client, name)
                for alias in list(found.aliases):
                    client.delete_registered_model_alias(found.name, alias)
                for version in client.search_model_versions(f"name='{found.name}'"):
                    client.delete_model_version(found.name, version.version)
                client.delete_registered_model(found.name)
        # Reverse creation order: views and governed table before its UDF dependencies.
        order = ["seats_live", "bookings_clean", "bookings_bronze", "doc_chunks", "event_forecast",
                 "attendance_predictions", "booking_features", "bookings_governed", "city_filter",
                 "mask_email", "event_metrics", "event_availability", "feedback", "bookings", "events", "raw"]
        for key in order:
            if key in present:
                course.guard(key)
                if OBJECTS[key][0] == "pipeline_table":
                    # Deleting a pipeline leaves its tables behind, and DROP needs the exact kind of table.
                    workspace.tables.delete(f"{course.cfg.catalog}.{course.cfg.schema}.{course.name(key)}")
                    continue
                kind = OBJECTS[key][0].upper()
                course.run(f"DROP {kind} {course.t(key)}")
        if experiment and experiment.lifecycle_stage != "deleted":
            client.delete_experiment(experiment.experiment_id)
    return {"endpoint_deleted": bool(endpoint), "data_objects_deleted": len(present),
            "model_deleted": bool(model), "agent_endpoint_deleted": bool(agent_endpoint),
            "agent_model_deleted": bool(agent_model), "pipeline_deleted": bool(pipeline),
            "job_deleted": bool(job), "app_deleted": bool(app), "vector_index_deleted": index is not None,
            "vector_endpoint_deleted": vector_endpoint is not None}
