"""Plain-Python pieces of Module 15: release records, the Champion alias move, rollback and a canary traffic split.

The registry client is passed in (an MLflowClient in the notebook), so the rules can be tested offline. The canary
bodies are plain dicts for the serving REST API, which avoids SDK class differences between versions.
"""
import pandas as pd

ALIAS = "Champion"


def predict_with_model(model):
    """Turn a loaded pyfunc model into the question -> {answer, status, steps} function the scorers read."""
    def predict(question):
        row = model.predict(pd.DataFrame({"question": [question]})).iloc[0]
        return {"answer": row["answer"], "status": row["status"], "steps": row["steps"]}  # steps: one joined string
    return predict


def release_record(verdict, run_id, compared_with):
    """The tags that make a version's release decision auditable: result, reasons, evidence and the rival."""
    return {"gate": "passed" if verdict["passed"] else "blocked",
            "gate_reasons": "; ".join(verdict["reasons"]) or "none",
            "evaluation_run_id": run_id, "compared_with_version": str(compared_with)}


def record_and_release(client, name, version, verdict, run_id, champion):
    """Write the release record on `version`, then move Champion to it only if the gate passed. True if moved."""
    for key, value in release_record(verdict, run_id, champion).items():
        client.set_model_version_tag(name, version, key, value)
    if not verdict["passed"]:
        return False
    client.set_model_version_tag(name, version, "replaces", str(champion))  # the rollback target
    client.set_registered_model_alias(name, ALIAS, version)
    return True


def roll_back(client, name):
    """Move Champion back to the version it replaced and mark the withdrawn one. Returns the restored version."""
    current = client.get_model_version_by_alias(name, ALIAS)
    target = (current.tags or {}).get("replaces")
    if not target:
        raise ValueError(f"Version {current.version} has no 'replaces' tag, so there is nothing to roll back to.")
    client.set_registered_model_alias(name, ALIAS, target)
    client.set_model_version_tag(name, current.version, "withdrawn", "yes")
    return str(target)


def _entity(name, model, version):
    return {"name": name, "entity_name": model, "entity_version": str(version), "workload_size": "Small",
            "scale_to_zero_enabled": True}


def canary_bodies(model, served_name, current_version, candidate_version, percent=10):
    """Bodies for PUT /api/2.0/serving-endpoints/<name>/config: (split, restore).

    The split keeps the running entity at 100 - percent and adds the candidate at `percent`; restore puts the
    endpoint back to the running version alone. Field names are not yet confirmed live: see docs/validation.md.
    """
    if not 0 < percent < 100:
        raise ValueError("percent must be between 1 and 99")
    split = {"served_entities": [_entity(served_name, model, current_version),
                                 _entity("candidate", model, candidate_version)],
             "traffic_config": {"routes": [{"served_model_name": served_name, "traffic_percentage": 100 - percent},
                                           {"served_model_name": "candidate", "traffic_percentage": percent}]}}
    restore = {"served_entities": [_entity(served_name, model, current_version)],
               "traffic_config": {"routes": [{"served_model_name": served_name, "traffic_percentage": 100}]}}
    return split, restore


def routes(endpoint):
    """{served name: percent} from a GET serving-endpoints reply (a dict)."""
    found = (endpoint.get("config") or {}).get("traffic_config", {}).get("routes", [])
    return {(r.get("served_model_name") or r.get("served_entity_name")): r.get("traffic_percentage") for r in found}
