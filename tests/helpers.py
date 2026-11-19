from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "event_assistant"
sys.path[:0] = [str(APP), str(ROOT / "course")]

from logic import load_events, ownership_marker


class Row(dict):
    def asDict(self):
        return dict(self)


class Frame:
    def __init__(self, rows, spark=None):
        self.rows = rows
        self.spark = spark

    def collect(self):
        return [Row(r) for r in self.rows]

    def select(self, *columns):
        return self

    def createOrReplaceTempView(self, name):
        self.spark.view = name
        self.spark.view_rows = self.rows


class FakeSpark:
    """Records SQL intent, not an emulator or proof of Spark/Delta correctness."""
    def __init__(self, exists=False, marker=None, rows=None):
        self.exists = exists
        self.marker = marker if marker is not None else ownership_marker("learner07")
        self.rows = load_events() if rows is None else rows
        self.statements = []
        self.dropped_views = []
        self.catalog = self
        self.fail_create = False

    def tableExists(self, table):
        return self.exists

    def dropTempView(self, name):
        self.dropped_views.append(name)

    def table(self, table):
        return Frame(self.rows)

    def createDataFrame(self, rows, schema=None):
        return Frame(rows, self)

    def sql(self, sql):
        self.statements.append(sql)
        if sql.startswith("DESCRIBE"):
            return Frame([{"col_name": "Comment", "data_type": self.marker}])
        if sql.startswith("CREATE TABLE"):
            if self.fail_create:
                raise RuntimeError("injected create failure")
            self.exists = True
            self.rows = self.view_rows
        if sql.startswith("DROP TABLE"):
            self.exists = False
        return Frame([])
