"""Helpers shared by the A8 course notebooks.

Notebooks load this through `notebooks/_config`. Nothing here runs a cloud action at
import time; every write is an explicit method call made from a notebook cell.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from . import exercises

COURSE_ID = "a8-databricks-learning"
SIMPLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
TAG = re.compile(r"[a-z][a-z0-9]{1,11}")

# Logical object -> (object type, module that creates it). Physical name: a8_<tag>_<key>.
OBJECTS = {
    "raw": ("volume", "01_lakehouse_data"),
    "events": ("table", "01_lakehouse_data"),
    "bookings": ("table", "01_lakehouse_data"),
    "feedback": ("table", "01_lakehouse_data"),
    "event_availability": ("view", "01_lakehouse_data"),
    "event_metrics": ("view", "03_descriptive_analytics"),
    "bookings_governed": ("table", "02_governance"),
    "mask_email": ("function", "02_governance"),
    "city_filter": ("function", "02_governance"),
    "booking_features": ("table", "05_predictive_ml"),
    "attendance_model": ("model", "05_predictive_ml"),
    "attendance_predictions": ("table", "05_predictive_ml"),
    "event_forecast": ("view", "05_predictive_ml"),
    "doc_chunks": ("table", "08b_rag"),
    "agent_model": ("model", "12_deploy_and_govern"),
    "bookings_bronze": ("pipeline_table", "13_pipelines_and_jobs"),
    "bookings_clean": ("pipeline_table", "13_pipelines_and_jobs"),
    "seats_live": ("pipeline_table", "13_pipelines_and_jobs"),
}


def derive_tag(email: str) -> str:
    """Suggest a learner tag from an email address, e.g. jsmith1974@... -> jsmith1974."""
    local = re.sub(r"[^a-z0-9]", "", (email or "").split("@")[0].lower())
    if not local or not local[0].isalpha():
        local = "learner" + local
    return local[:12] if len(local) >= 2 else "learner"


def validate_tag(tag: str) -> str:
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise ValueError(
            "Learner tag: 2-12 characters, lowercase letters and digits only, starting with a letter "
            f"(got {tag!r})."
        )
    return tag


def quote(part: str) -> str:
    """Quote one Unity Catalog name part. Backticks are rejected rather than escaped."""
    if not isinstance(part, str) or not part or "`" in part or "." in part:
        raise ValueError(f"Invalid catalog, schema or object name: {part!r}")
    return part if SIMPLE_NAME.fullmatch(part) else f"`{part}`"


def sql_string(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


@dataclass
class Config:
    catalog: str
    schema: str
    tag: str
    user: str
    host: str
    chat_model: str = ""
    embedding_model: str = ""
    warehouse_id: str = ""
    saved_at: str = ""

    def validate(self) -> "Config":
        quote(self.catalog)
        quote(self.schema)
        validate_tag(self.tag)
        if self.catalog in {"system", "samples", "dbacademy"}:
            raise ValueError("Choose your own writable catalog, not a system or sample catalog.")
        return self

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known}).validate()


def config_path(user: str, profile: str = "default") -> Path:
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", profile or ""):
        raise ValueError("Profile names use lowercase letters, digits, hyphens and underscores.")
    return Path("/Workspace/Users") / user / "a8learn" / f"{profile}.json"


class Course:
    """The course context for one learner: names, links, checks and safe writes."""

    def __init__(self, config: Config, spark=None, display=None, display_html=None, dbutils=None,
                 root: Path | None = None, answers: str = ""):
        self.cfg = config.validate()
        self.spark, self._display, self._html, self.dbutils = spark, display, display_html, dbutils
        self.root = root
        self.test_with_solutions = answers == "solutions"

    # ---------- configuration ----------
    @staticmethod
    def save(config: Config, profile: str = "default") -> Path:
        config.validate()
        config.saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = config_path(config.user, profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, spark, user: str, profile: str = "default", **kwargs) -> "Course":
        path = config_path(user, profile)
        if not path.is_file():
            raise FileNotFoundError(
                f"No course configuration found at {path}. Open notebooks/00_setup and run it first."
            )
        return cls(Config.from_dict(json.loads(path.read_text(encoding="utf-8"))), spark=spark, **kwargs)

    # ---------- names ----------
    @property
    def prefix(self) -> str:
        return f"a8_{self.cfg.tag}_"

    def name(self, key: str) -> str:
        if key not in OBJECTS and key != "setup_probe":
            raise KeyError(f"Unknown course object {key!r}")
        return self.prefix + key

    def t(self, key: str) -> str:
        """Fully qualified, quoted name, ready for SQL."""
        return ".".join(quote(p) for p in (self.cfg.catalog, self.cfg.schema, self.name(key)))

    @property
    def schema_fqn(self) -> str:
        return f"{quote(self.cfg.catalog)}.{quote(self.cfg.schema)}"

    @property
    def volume_path(self) -> str:
        return f"/Volumes/{self.cfg.catalog}/{self.cfg.schema}/{self.name('raw')}"

    @property
    def experiment_path(self) -> str:
        return f"/Users/{self.cfg.user}/a8learn_{self.cfg.tag}_attendance"

    @property
    def evaluation_experiment_path(self) -> str:
        """Experiment holding Module 14's evaluation runs and traces, apart from the attendance model's."""
        return f"/Users/{self.cfg.user}/a8learn_{self.cfg.tag}_agent_eval"

    @property
    def dashboard_path(self) -> Path:
        """Module 3's generated dashboard file, beside the learner's saved settings."""
        return config_path(self.cfg.user).parent / f"A8 {self.cfg.tag} event snapshot.lvdash.json"

    @property
    def endpoint_name(self) -> str:
        return f"a8-{self.cfg.tag}-attendance"

    @property
    def agent_endpoint_name(self) -> str:
        """This learner's agent serving endpoint (Module 12). Billable while it exists."""
        return f"a8-{self.cfg.tag}-agent"

    @property
    def agent_model_name(self) -> str:
        """Three-part Unity Catalog name of this learner's registered agent model (Module 12)."""
        return f"{self.cfg.catalog}.{self.cfg.schema}.{self.name('agent_model')}"

    @property
    def pipeline_name(self) -> str:
        """This learner's bookings pipeline (Module 13)."""
        return f"a8-{self.cfg.tag}-bookings"

    @property
    def job_name(self) -> str:
        """This learner's scheduled refresh job (Module 13)."""
        return f"a8-{self.cfg.tag}-refresh"

    @property
    def app_name(self) -> str:
        """This learner's seats-left app (Module 11). Runs compute while it exists."""
        return f"a8-{self.cfg.tag}-events"

    @property
    def app_folder(self) -> str:
        """Workspace folder holding the generated app source (Module 11); deploy it as /Workspace + this."""
        return f"/Users/{self.cfg.user}/a8learn_{self.cfg.tag}_app"

    @property
    def incoming_path(self) -> str:
        """Volume folder where new booking files land (Module 13)."""
        return f"{self.volume_path}/incoming"

    @property
    def vector_endpoint_name(self) -> str:
        """This learner's Vector Search endpoint (Module 8c). Billable while it exists."""
        return f"a8-{self.cfg.tag}-vs"

    @property
    def vector_index_name(self) -> str:
        """Three-part, unquoted name of this learner's Vector Search index, as the SDK expects it."""
        return f"{self.cfg.catalog}.{self.cfg.schema}.{self.prefix}doc_index"

    @property
    def model_name(self) -> str:
        """Three-part Unity Catalog name of this learner's registered model."""
        return f"{self.cfg.catalog}.{self.cfg.schema}.{self.name('attendance_model')}"

    @property
    def course_tags(self) -> dict:
        """MLflow, model and endpoint tags. UC model tag keys reject '.', hence underscores."""
        return {"a8learn_course": COURSE_ID, "a8learn_tag": self.cfg.tag}

    def fmt(self, sql: str) -> str:
        """Replace {events}, {bookings}, {volume_path}, {schema}, {tag} ... with real names."""
        extras = {"schema": self.schema_fqn, "catalog": quote(self.cfg.catalog), "tag": self.cfg.tag,
                  "volume_path": self.volume_path, "user": self.cfg.user,
                  "chat_model": self.cfg.chat_model, "endpoint": self.endpoint_name}

        def replace(match):
            key = match.group(1)
            if key in OBJECTS:
                return self.t(key)
            return extras.get(key, match.group(0))

        return re.sub(r"\{([a-z_]+)\}", replace, sql)

    def declare_variables(self):
        """SQL session variables so %sql cells can use IDENTIFIER(a8_events) etc."""
        statements = [f"DECLARE OR REPLACE VARIABLE a8_{key} STRING DEFAULT {sql_string(self.t(key))}"
                      for key in OBJECTS]
        statements.append(f"DECLARE OR REPLACE VARIABLE a8_schema STRING DEFAULT {sql_string(self.schema_fqn)}")
        for statement in statements:
            self.spark.sql(statement)

    # ---------- reading state ----------
    def _info(self, key: str):
        kind = OBJECTS[key][0]
        catalog = quote(self.cfg.catalog)
        name = sql_string(self.name(key))
        schema = sql_string(self.cfg.schema)
        query = {
            "table": f"SELECT table_owner AS owner FROM {catalog}.information_schema.tables "
                     f"WHERE table_schema = {schema} AND table_name = {name}",
            "view": f"SELECT table_owner AS owner FROM {catalog}.information_schema.tables "
                    f"WHERE table_schema = {schema} AND table_name = {name}",
            "pipeline_table": f"SELECT table_owner AS owner FROM {catalog}.information_schema.tables "
                              f"WHERE table_schema = {schema} AND table_name = {name}",
            "volume": f"SELECT volume_owner AS owner FROM {catalog}.information_schema.volumes "
                      f"WHERE volume_schema = {schema} AND volume_name = {name}",
            "function": f"SELECT routine_owner AS owner FROM {catalog}.information_schema.routines "
                        f"WHERE routine_schema = {schema} AND routine_name = {name}",
        }.get(kind)
        if query is None:
            return None
        rows = self.spark.sql(query).collect()
        return rows[0]["owner"] if rows else None

    def exists(self, key: str) -> bool:
        if OBJECTS[key][0] == "model":
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.errors import NotFound
            try:
                WorkspaceClient().registered_models.get(
                    f"{self.cfg.catalog}.{self.cfg.schema}.{self.name(key)}")
                return True
            except NotFound:
                return False
        return self._info(key) is not None

    def guard(self, key: str):
        """Stop before replacing an object somebody else owns."""
        owner = self._info(key)
        if owner is not None and owner != self.cfg.user:
            raise PermissionError(
                f"{self.t(key)} already exists and is owned by {owner}, not you. "
                "Nothing was changed. Choose a different learner tag in 00_setup."
            )
        if owner is not None:
            kind = OBJECTS[key][0]
            source, schema_col, name_col, comment_col = {
                "table": ("tables", "table_schema", "table_name", "comment"),
                "view": ("tables", "table_schema", "table_name", "comment"),
                "pipeline_table": ("tables", "table_schema", "table_name", "comment"),
                "volume": ("volumes", "volume_schema", "volume_name", "comment"),
                "function": ("routines", "routine_schema", "routine_name", "comment"),
            }[kind]
            rows = self.spark.sql(
                f"SELECT {comment_col} AS marker FROM {quote(self.cfg.catalog)}.information_schema.{source} "
                f"WHERE {schema_col} = {sql_string(self.cfg.schema)} "
                f"AND {name_col} = {sql_string(self.name(key))}"
            ).collect()
            if not rows or not (rows[0]["marker"] or "").startswith(COURSE_ID + " "):
                raise PermissionError(f"{self.t(key)} is not marked as course work. Choose another tag.")

    def require(self, *keys: str):
        missing = [k for k in keys if not self.exists(k)]
        if not missing:
            return
        items = "".join(f"<li><code>{html.escape(self.name(k))}</code>, created in "
                        f"<b>{OBJECTS[k][1]}</b></li>" for k in missing)
        self.card("This module needs earlier work",
                  f"<p>These objects are missing:</p><ul>{items}</ul>"
                  "<p>Run the named notebook(s) first, then come back. Your configuration is fine.</p>",
                  tone="warn")
        raise RuntimeError("Missing prerequisites: " + ", ".join(self.name(k) for k in missing))

    # ---------- MLflow ownership checks ----------
    def _is_course_run(self, tags) -> bool:
        return all((tags or {}).get(k) == v for k, v in self.course_tags.items())

    def claim_experiment(self, client, path=None):
        """Refuse a foreign experiment at our path; restore ours if cleanup soft-deleted it.

        Must run before mlflow.set_experiment, which cannot select a deleted experiment
        and would otherwise silently adopt somebody else's.
        """
        path = path or self.experiment_path
        experiment = client.get_experiment_by_name(path)
        if experiment is None:
            return
        if not self._is_course_run(experiment.tags):
            raise PermissionError(
                f"{path} exists but is not marked as this course run. "
                "Nothing was changed. Choose another learner tag in 00_setup.")
        if experiment.lifecycle_stage == "deleted":
            client.restore_experiment(experiment.experiment_id)

    def mark_experiment(self, client, experiment):
        for key, value in self.course_tags.items():
            client.set_experiment_tag(experiment.experiment_id, key, value)

    def claim_model(self, client, workspace, name=None):
        """Create the registered model with course tags, or confirm an existing one is ours."""
        name = name or self.model_name
        try:
            existing = client.get_registered_model(name)
        except Exception as error:
            if getattr(error, "error_code", None) != "RESOURCE_DOES_NOT_EXIST":
                raise
            client.create_registered_model(name, tags=self.course_tags)
            return
        if not self._is_course_run(existing.tags):
            raise PermissionError(f"{name} is not marked as this course run. Choose another tag.")
        if workspace.registered_models.get(name).owner != self.cfg.user:
            raise PermissionError(f"{name} is not owned by you. Choose another tag.")

    # ---------- running SQL ----------
    def sql(self, sql: str):
        return self.spark.sql(self.fmt(sql))

    def run(self, sql: str, show_sql: bool = True):
        """Run one statement and show the exact SQL that ran, with your real names."""
        resolved = self.fmt(sql).strip()
        if show_sql:
            self.code(resolved)
        return self.spark.sql(resolved)

    def create_table(self, key: str, select_sql: str, comment: str):
        self.guard(key)
        statement = (
            f"CREATE OR REPLACE TABLE {self.t(key)}\n"
            f"COMMENT {sql_string(comment)}\n"
            f"TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{self.cfg.tag}')\n"
            f"AS {self.fmt(select_sql).strip()}"
        )
        self.code(statement)
        self.spark.sql(statement)
        return self.t(key)

    # ---------- checks ----------
    def expect(self, condition, message: str):
        """A notebook check: raise a readable error, or confirm what passed. Unlike assert, never skipped."""
        if not condition:
            self.card("Check failed", f"<p>{html.escape(message)}</p>", tone="bad")
            raise AssertionError(message)
        print("✓", message)

    # ---------- display ----------
    def html(self, body: str):
        if self._html is None:
            print(re.sub(r"<[^>]+>", "", body))
        else:
            self._html(body)

    def card(self, title: str, body_html: str, tone: str = "info"):
        accent = {"info": "#1d2225", "ok": "#1b7f3b", "warn": "#a93614", "bad": "#b00020"}[tone]
        # A8 text branding: ink panel, orange rule on top, tone colour on the left. Palette is provisional.
        self.html(
            f'<div style="border-top:3px solid #ff5b35;border-left:6px solid {accent};background:#f7f7f7;'
            f'padding:12px 16px;margin:6px 0;font-family:Arial,Helvetica,sans-serif;color:#1d2225;line-height:1.5">'
            f'<div style="font-weight:700;font-size:15px;margin-bottom:4px">'
            f'<span style="color:#a93614">A8</span> | {html.escape(title)}</div>'
            f"{body_html}</div>"
        )

    def code(self, text: str):
        self.html('<pre style="background:#1d2225;color:#f2f2f2;padding:10px 12px;border-radius:4px;'
                  'font-size:12px;white-space:pre-wrap">' + html.escape(text) + "</pre>")

    def url(self, kind: str, name: str = "") -> str:
        h, c, s = self.cfg.host.rstrip("/"), self.cfg.catalog, self.cfg.schema
        return {
            "schema": f"{h}/explore/data/{c}/{s}",
            "table": f"{h}/explore/data/{c}/{s}/{name}",
            "volume": f"{h}/explore/data/volumes/{c}/{s}/{name}",
            "function": f"{h}/explore/data/functions/{c}/{s}/{name}",
            "model": f"{h}/explore/data/models/{c}/{s}/{name}",
            "experiment": f"{h}/ml/experiments/{name}",
            "endpoint": f"{h}/ml/endpoints/{name}",
            "sql_editor": f"{h}/sql/editor",
            "playground": f"{h}/ml/playground",
            "serving": f"{h}/ml/endpoints",
            "vector_search": f"{h}/compute/vector-search",
            "apps": f"{h}/apps",
            "app": f"{h}/apps/{name}",
            "jobs": f"{h}/jobs",
            "job": f"{h}/jobs/{name}",
            "pipeline": f"{h}/pipelines/{name}",
        }[kind]

    def links(self, *items):
        """items: (label, kind, key_or_name). key may be a course object key."""
        parts = []
        for label, kind, name in items:
            target = self.name(name) if name in OBJECTS else name
            parts.append(f'<li><a href="{html.escape(self.url(kind, target))}" target="_blank" '
                         f'style="color:#a93614;font-weight:700">{html.escape(label)}</a></li>')
        self.card("Open in the Databricks UI", "<ul style='margin:4px 0'>" + "".join(parts) + "</ul>")

    # ---------- exercises ----------
    def check(self, exercise_id: str, answer=None) -> bool:
        ex = exercises.get(exercise_id)
        blank = answer is None or (isinstance(answer, str) and not answer.strip())
        if blank and self.test_with_solutions:
            answer = ex["solution"]
            blank = False
        if blank:
            self.card(f"{exercise_id}: not attempted yet",
                      f"<p>{html.escape(ex['task'])}</p><p><b>Hint:</b> {html.escape(ex['hint'])}</p>"
                      f"<p>Answer with a SQL string, a Spark DataFrame or a pandas DataFrame.</p>"
                      f"<p>Stuck? Run <code>A8.solution('{exercise_id}')</code>.</p>", tone="warn")
            return False
        try:
            actual = self._rows(answer)
            expected = self._rows(ex["solution"])
        except Exception as error:  # learner SQL errors are expected while learning
            self.card(f"{exercise_id}: your answer did not run",
                      f"<pre style='white-space:pre-wrap'>{html.escape(str(error)[:600])}</pre>"
                      f"<p><b>Hint:</b> {html.escape(ex['hint'])}</p>", tone="bad")
            return False
        ok, detail = compare(actual, expected, ordered=ex.get("ordered", False))
        if ok:
            self.card(f"{exercise_id}: correct", f"<p>{html.escape(ex['explain'])}</p>", tone="ok")
        else:
            self.card(f"{exercise_id}: not quite",
                      f"<p>{html.escape(detail)}</p><p><b>Hint:</b> {html.escape(ex['hint'])}</p>",
                      tone="bad")
        if self.test_with_solutions and not ok:
            raise AssertionError(f"Instructor validation failed for {exercise_id}: {detail}")
        return ok

    def _rows(self, answer):
        if isinstance(answer, str):
            answer = self.sql(answer)
        if hasattr(answer, "itertuples"):  # a pandas DataFrame: plain Python values, NaN as None
            def plain(value):
                value = value.item() if hasattr(value, "item") else value
                return None if value != value else value
            return list(answer.columns), [tuple(plain(v) for v in row) for row in answer.itertuples(index=False)]
        if hasattr(answer, "collect"):
            columns = list(answer.columns)
            return columns, [tuple(r) for r in answer.collect()]
        return ["value"], [(answer,)]

    def reflect(self, reflection_id: str, answer: str = ""):
        """Ask for an answer in the learner's own words, then show a model answer to compare with."""
        item = exercises.get_reflection(reflection_id)
        if not (answer or "").strip():
            self.card(f"{reflection_id}: in your own words",
                      f"<p>{html.escape(item['question'])}</p>"
                      "<p>Write one or two sentences between the quotes above, then run this cell again.</p>",
                      tone="warn")
            return False
        self.card(f"{reflection_id}: compare",
                  f"<p><b>Your answer:</b> {html.escape(answer.strip())}</p>"
                  f"<p><b>One good answer:</b> {html.escape(item['model'])}</p>"
                  "<p>Different wording is fine. Check that you have the same idea.</p>", tone="ok")
        return True

    def solution(self, exercise_id: str):
        ex = exercises.get(exercise_id)
        self.card(f"Solution, {exercise_id}", f"<p>{html.escape(ex['explain'])}</p>")
        self.code(ex["solution"].strip())

    def gate(self, name: str, label: str) -> bool:
        """A yes/no switch for billable or destructive steps. Defaults to no."""
        try:
            self.dbutils.widgets.dropdown(name, "no", ["no", "yes"], label)
        except Exception:
            pass
        try:
            return self.dbutils.widgets.get(name) == "yes"
        except Exception:
            return False

    def next_step(self, built: list[str], next_notebook: str | None, next_title: str = ""):
        items = "".join(f"<li>{html.escape(b)}</li>" for b in built)
        nxt = (f"<p><b>Next:</b> open <code>notebooks/{html.escape(next_notebook)}</code>"
               f"{' – ' + html.escape(next_title) if next_title else ''}.</p>") if next_notebook else ""
        self.card("Module complete", f"<p>You built:</p><ul>{items}</ul>{nxt}"
                  "<p>Pausing? Optional serving endpoints remain billable until deleted, even if "
                  "compute idles. See <code>notebooks/99_pause_and_cleanup</code>.</p>", tone="ok")


def _normal(value):
    # Spark DECIMAL and pandas floats must compare alike without losing an exercise's third decimal.
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        return round(number, 9).normalize() if number.is_finite() else number
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def compare(actual, expected, ordered=False):
    """Compare (columns, rows) pairs. Column names are not compared, only count and values."""
    a_cols, a_rows = actual
    e_cols, e_rows = expected
    if len(a_cols) != len(e_cols):
        return False, (f"Expected {len(e_cols)} column(s) ({', '.join(e_cols)}), "
                       f"got {len(a_cols)} ({', '.join(a_cols)}).")
    a = [tuple(_normal(v) for v in r) for r in a_rows]
    e = [tuple(_normal(v) for v in r) for r in e_rows]
    if not ordered:
        a, e = sorted(a, key=repr), sorted(e, key=repr)
    if len(a) != len(e):
        return False, f"Expected {len(e)} row(s), got {len(a)}."
    for i, (x, y) in enumerate(zip(a, e, strict=True)):
        if x != y:
            where = "in row" if ordered else "in sorted row"
            return False, f"First difference {where} {i + 1}: got {x}, expected {y}."
    return True, ""
