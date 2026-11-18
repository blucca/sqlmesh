"""Run #6224's schema oracle and apply its DDL to synthetic DuckDB SCD history.
The metadata seam returns exactly the columns selected by the real adapter;
Scope: offline planner/metadata checks and synthetic DuckDB history execution.
"""

import argparse
import json
from unittest.mock import Mock
import duckdb  # noqa: TID253
from sqlglot import exp
from sqlmesh.core.schema_diff import (
    get_schema_differ,
    get_additive_column_names,
    has_drop_alteration,
)
from sqlmesh.core.engine_adapter import MSSQLEngineAdapter, FabricEngineAdapter
from sqlmesh.core.engine_adapter.shared import CatalogSupport

parser = argparse.ArgumentParser()
parser.add_argument("--assert-fixed", action="store_true")
args = parser.parse_args()
results = {}
sd = get_schema_differ("fabric")
cur = {"v": exp.DataType.build("DATETIME2(6)", dialect="fabric")}
new = {"v": exp.DataType.build("TIMESTAMP"), "c": exp.DataType.build("BIT")}
ops = sd.compare_columns("t", cur, new)
results["author_repro"] = {
    "sql": [o.expression.sql("fabric") for o in ops],
    "destructive": has_drop_alteration(ops),
    "expected": "only ADD c",
    "pass": len(ops) == 1
    and get_additive_column_names(ops) == ["c"]
    and not has_drop_alteration(ops),
}

# The two managed SCD2 fields from the report, with independent literal history.
cur = {
    name: exp.DataType.build("DATETIME2(6)", dialect="fabric")
    for name in ("_dwh_valid_from", "_dwh_valid_to")
}
new = {name: exp.DataType.build("TIMESTAMP") for name in cur}
new["cancelled_flag"] = exp.DataType.build("BIT")
ops = sd.compare_columns("t", cur, new)
db = duckdb.connect(":memory:")
db.execute("CREATE TABLE t (id INTEGER, _dwh_valid_from TIMESTAMP, _dwh_valid_to TIMESTAMP)")
db.execute(
    "INSERT INTO t VALUES (1, '2026-01-01 00:00:00.123456', '2026-02-01 00:00:00.654321'), (1, '2026-02-01 00:00:00.654321', NULL), (2, '2026-03-01 00:00:00.000001', NULL)"
)
before = db.execute(
    "SELECT id, _dwh_valid_from, _dwh_valid_to FROM t ORDER BY id, _dwh_valid_from"
).fetchall()
for op in ops:
    db.execute(op.expression.sql("duckdb"))
after = db.execute(
    "SELECT id, _dwh_valid_from, _dwh_valid_to FROM t ORDER BY id, _dwh_valid_from"
).fetchall()
results["synthetic_scd_history"] = {
    "fabric_sql": [o.expression.sql("fabric") for o in ops],
    "before": before,
    "after": after,
    "expected": "only ADD cancelled_flag; all three history rows unchanged",
    "pass": len(ops) == 1
    and get_additive_column_names(ops) == ["cancelled_flag"]
    and before == after,
}
db.close()

for adapter_class in (MSSQLEngineAdapter, FabricEngineAdapter):
    connection, cursor = Mock(), Mock()
    connection.cursor.return_value = cursor
    cursor.fetchone.return_value = None
    # Information-schema fixture: old SELECT has five fields and loses precision.
    cursor.fetchall.side_effect = (
        lambda: [("v", "datetime2", None, None, None, 6)]
        if "DATETIME_PRECISION" in cursor.execute.call_args.args[0]
        else [("v", "datetime2", None, None, None)]
    )
    adapter = adapter_class(
        lambda *a, **kw: connection, catalog_support=CatalogSupport.REQUIRES_SET_CATALOG
    )
    got = adapter.columns("dbo.t")
    expected = {"v": exp.DataType.build("DATETIME2(6)", dialect=adapter.dialect)}
    results[adapter.dialect + "_metadata"] = {
        "query": cursor.execute.call_args.args[0],
        "type_sql": got["v"].sql(adapter.dialect),
        "explicit_precision": str(got["v"].expressions),
        "expected": "explicit DATETIME2(6)",
        "pass": got == expected,
    }
    adapter.close()
print(json.dumps(results, default=str, indent=2))
if args.assert_fixed:
    assert all(result["pass"] for result in results.values()), results
