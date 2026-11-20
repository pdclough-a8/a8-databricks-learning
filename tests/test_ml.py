"""Exercise the notebook's split and estimator code on independently derived features."""
import contextlib
import io
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]


class PredictiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        events = pd.read_csv(ROOT / "data/raw/events.csv", parse_dates=["event_date"])
        bookings = pd.read_csv(ROOT / "data/raw/bookings.csv", parse_dates=["booked_date"])
        joined = bookings[bookings.status == "confirmed"].merge(
            events.rename(columns={"status": "event_status"}), on="event_id", validate="many_to_one")
        joined["weekday"] = (joined.event_date.dt.dayofweek + 1) % 7 + 1  # Spark: Sunday=1
        joined["lead_days"] = (joined.event_date - joined.booked_date).dt.days
        joined["label"] = joined.attended.map({True: 1, False: 0})
        source = (ROOT / "notebooks/03_predictive_ml.py").read_text()
        cells = source.split("# COMMAND ----------")
        split_cell = next(c for c in cells if "\nframe = spark.table(" in c)
        baseline_cell = next(c for c in cells if "\nbaseline = DummyClassifier(" in c)
        model_cell = next(
            c for c in cells if "\npreprocess = ColumnTransformer(" in c
        ).split("with mlflow.start_run")[0]
        cls.env = {
            "spark": SimpleNamespace(table=lambda _: SimpleNamespace(toPandas=lambda: joined.copy())),
            "A8": SimpleNamespace(t=lambda _: "unused"),
            "DummyClassifier": DummyClassifier, "log_loss": log_loss,
            "ColumnTransformer": ColumnTransformer, "OneHotEncoder": OneHotEncoder,
            "StandardScaler": StandardScaler, "Pipeline": Pipeline,
            "LogisticRegression": LogisticRegression,
        }
        with contextlib.redirect_stdout(io.StringIO()):
            exec(split_cell, cls.env)
            exec(baseline_cell, cls.env)
            exec(model_cell, cls.env)
        cls.env["pipeline"].fit(cls.env["train"][cls.env["features"]], cls.env["train"].label)

    def test_event_split_and_label_availability(self):
        e = self.env
        self.assertEqual(e["test"].event_id.nunique(), 10)
        self.assertEqual(e["train"].event_id.nunique(), 38)
        self.assertEqual(e["future"].event_id.nunique(), 12)
        self.assertTrue(e["future"].label.isna().all())
        self.assertFalse(set(e["train"].event_id) & set(e["test"].event_id))
        self.assertLessEqual(e["train"].event_date.max(), e["test"].event_date.min())

    def test_real_pipeline_probabilities_and_forecast_bounds(self):
        e = self.env
        p = e["pipeline"].predict_proba(e["future"][e["features"]])
        self.assertEqual(list(e["pipeline"].classes_), [0, 1])
        self.assertEqual(p.shape, (len(e["future"]), 2))
        self.assertTrue(np.allclose(p.sum(axis=1), 1))
        self.assertTrue(((p >= 0) & (p <= 1)).all())
        forecast = e["future"][["event_id", "tickets"]].copy()
        forecast["expected"] = forecast.tickets * p[:, 1]
        totals = forecast.groupby("event_id")[["tickets", "expected"]].sum()
        self.assertTrue((totals.expected <= totals.tickets).all())
        self.assertTrue((totals.expected >= 0).all())

    def test_model_beats_the_baseline_on_holdout_log_loss(self):
        e = self.env
        probabilities = e["pipeline"].predict_proba(e["test"][e["features"]])[:, 1]
        self.assertLess(log_loss(e["test"].label, probabilities), e["baseline_loss"])

    def test_no_identifiers_outcomes_or_contacts_in_features(self):
        self.assertFalse(set(self.env["features"]) & {
            "label", "attended", "customer_email", "customer_name", "event_id", "event_date", "booking_id"})


if __name__ == "__main__":
    unittest.main()
