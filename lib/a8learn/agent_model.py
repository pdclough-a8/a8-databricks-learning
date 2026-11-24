"""MLflow wrapper for the A8 Events support agent ("models from code").

MLflow runs this file when it loads the model, so it must call set_model at the end. The agent logic is in
agent_core.py, which is logged beside it. The model takes a table with one text column, question, and returns one
row per question with answer, status and the tools used.
"""
import json

import mlflow
import pandas as pd
from agent_core import answer
from mlflow.pyfunc import PythonModel


class A8Agent(PythonModel):
    def load_context(self, context):
        with open(context.artifacts["snapshot"], encoding="utf-8") as handle:
            self.snapshot = json.load(handle)

    def predict(self, context, model_input, params=None):
        results = [answer(self.snapshot, str(question)) for question in model_input["question"]]
        return pd.DataFrame({"answer": [r["answer"] for r in results], "status": [r["status"] for r in results],
                             "steps": [",".join(r["steps"]) for r in results]})


mlflow.models.set_model(A8Agent())
