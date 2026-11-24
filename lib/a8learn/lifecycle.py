"""Exact-name, owner/marker checked teardown; no list-and-prefix deletion."""

import time

from . import COURSE_ID, OBJECTS


def endpoint_for_cleanup(course, workspace):
    from databricks.sdk.errors import NotFound
    try:
        endpoint = workspace.serving_endpoints.get(course.endpoint_name)
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


def model_for_cleanup(course, workspace, client):
    import mlflow
    name = course.model_name
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
    index, vector_endpoint = vector_search_for_cleanup(course, workspace)
    keys = [k for k in reversed(OBJECTS) if OBJECTS[k][0] != "model"] if tables else []
    present = [k for k in keys if course.exists(k)]
    # Preflight every intended target before the first delete.
    for key in present:
        course.guard(key)
    model = model_for_cleanup(course, workspace, client) if tables else None
    experiment = client.get_experiment_by_name(course.experiment_path) if tables else None
    if experiment and (experiment.tags.get("a8learn_course") != COURSE_ID or
                       experiment.tags.get("a8learn_tag") != course.cfg.tag):
        raise PermissionError("Experiment has no matching course tags. Nothing deleted.")
    if endpoint:
        endpoint_for_cleanup(course, workspace)
        workspace.serving_endpoints.delete(course.endpoint_name)
    if index is not None or vector_endpoint is not None:
        vector_search_for_cleanup(course, workspace)
        delete_vector_search(course, workspace, index, vector_endpoint)
    if tables:
        if model:
            model_for_cleanup(course, workspace, client)
            for alias in list(model.aliases):
                client.delete_registered_model_alias(model.name, alias)
            for version in client.search_model_versions(f"name='{model.name}'"):
                client.delete_model_version(model.name, version.version)
            client.delete_registered_model(model.name)
        # Reverse creation order: views and governed table before its UDF dependencies.
        order = ["doc_chunks", "event_forecast", "attendance_predictions", "booking_features",
                 "bookings_governed", "city_filter", "mask_email", "event_metrics", "event_availability",
                 "feedback", "bookings", "events", "raw"]
        for key in order:
            if key in present:
                course.guard(key)
                kind = OBJECTS[key][0].upper()
                course.run(f"DROP {kind} {course.t(key)}")
        if experiment and experiment.lifecycle_stage != "deleted":
            client.delete_experiment(experiment.experiment_id)
    return {"endpoint_deleted": bool(endpoint), "data_objects_deleted": len(present),
            "model_deleted": bool(model), "vector_index_deleted": index is not None,
            "vector_endpoint_deleted": vector_endpoint is not None}
