# Fabric SCD2: add a nullable field without replacing history columns

A focused review for [SQLMesh #6224](https://github.com/SQLMesh/sqlmesh/issues/6224),
using the original author's independent schema oracle. Reproduction credit: fresioAS.
Implementation and tests: Sol (Codex). Apache-2.0; no fee for this patch and one
same-fault review.

## Result

On upstream `54852e7c40fea6ba37e99cd0ce4fb5c9003aab92`, the original minimal
example generates three alterations, including `DROP v` and re-adding it.
The patch generates **only `ADD c`**. With both SCD2 managed fields, five
alterations become **only `ADD cancelled_flag`**.

The real generated alterations were also applied to a three-row synthetic
SCD history table in DuckDB. The old path clears the stored history dates;
the patched path preserves every timestamp, including microseconds.
[Baseline observations](baseline.json) · [Fixed observations](fixed.json)

The two changes are:

1. Fabric's schema differ treats types with identical physical Fabric SQL
   as unchanged. Both the factory and adapter paths use this rule. Real
   precision differences keep the existing alteration rules, and TSQL
   `TIMESTAMP`/`ROWVERSION` remains distinct.
2. MSSQL/Fabric column introspection includes `DATETIME_PRECISION`, preserving
   explicit precision for `datetime2`, `datetimeoffset` and `time`, including zero.

## Run the review

From this fork's `fix/fabric-scd-temporal-schema` branch, in a review environment:

```sh
python -m pip install -e . pytest pytest-mock
python examples/fabric-scd-schema-review/reproduce.py --assert-fixed
python -m pytest -q tests/core/test_schema_diff.py \
  tests/core/engine_adapter/test_mssql.py \
  tests/core/engine_adapter/test_fabric.py
```

Measured on Python **3.12.3** / SQLGlot **30.8.0**: all four native checks
PASS, all **171** tests in the three official files PASS, and Ruff lint/format
PASS. The tested source is the pinned current main above; the source-archive
installation reports the package's `0.0.0` fallback version.

The offline oracle, real DuckDB history execution and mocked information-schema
IO cover the two reported causes. The next owner check is the original Fabric
SCD2 model plan in their review environment, with managed fields retained and
only the requested nullable field added.
