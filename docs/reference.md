# Reference and glossary

## Follow the data

```text
Synthetic events.csv -> lesson 1 Unity Catalog table -> learner's SQL checks
         |
         +-> lesson 2: full records in a prompt -> model answer -> human verdict
         |
         +-> packaged app CSV -> simulation OR one live model request -> checked answer
```

There is intentionally no runtime arrow from the Unity Catalog table to the app.
The shared scenario and fixture connect the lessons; a live data dependency comes later.

| Term | Meaning here |
|---|---|
| Catalog / schema / table | Three levels in the table's fully qualified name |
| Fixture | Fixed synthetic records with independently checkable expected facts |
| Prompt context | Records explicitly supplied in the model request |
| RAG | Retrieval selects external evidence before generation; absent in this pilot |
| Serving endpoint | Existing approved model API destination, not created by the course |
| Simulation | Deterministic code, no model authentication or inference |
| App service principal | Workload identity used for deployed app calls |
| Model resource | App configuration granting its identity endpoint query access |
| Snapshot deployment | Deployed source copy; later workspace edits need redeployment |
| Ownership marker | Exact course/tag comment or description to avoid accidental collisions |
| Checkpoint | Working result plus the learner's explanation and transfer evidence |

## Source map

| Location | Purpose |
|---|---|
| `notebooks/` | Browser-first runnable Databricks sources |
| `app/event_assistant/logic.py` | CSV validation, naming, prompts, simulation and injected live client |
| `app/event_assistant/app.py` | Supplied Streamlit interface |
| `course/workspace_ops.py` | Explicit table/app lifecycle helpers, no import-time cloud actions |
| `solutions/01_data.py` | Full gap solution, after trying |
| `prompts/tutor.md` | Portable optional tutor contract |
| `tests/` | Offline checks, not cloud acceptance |

## Platform documentation

UI labels and feature availability vary by cloud, region, workspace policy and release.
These official Azure Databricks pages describe the integration pattern; use your cloud's equivalent
and confirm against your target workspace before teaching:

- [Git folders](https://learn.microsoft.com/en-us/azure/databricks/repos/)
- [Import and export notebooks](https://learn.microsoft.com/en-us/azure/databricks/notebooks/notebook-export-import)
- [Apps model-serving resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/model-serving)
- [Deploy an app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy)
- [Query foundation models](https://learn.microsoft.com/en-us/azure/databricks/machine-learning/model-serving/score-foundation-models)
- [Apps gateway model services](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/unity-gateway)

The pinned SDK exposes the serving-endpoint OpenAI-compatible client used here.
This is not a claim that every model supports the same parameters, or that legacy endpoints are
the preferred new architecture. Ask the instructor if only gateway model services are enabled.
