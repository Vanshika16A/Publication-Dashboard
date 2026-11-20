"""Create a DuckDB database over the dataset, network files and raw snapshot.

    python -m dpcn_mapping.duckdb_setup             # reload the CSV tables, refresh raw views
    python -m dpcn_mapping.duckdb_setup --parquet   # also convert the snapshot JSONL to Parquet

The database (data/duckdb/group16.duckdb) stores the processed and network CSVs as tables,
so queries do not re-parse text; rerun this after every build to pick up new files. Raw
snapshot data stays outside the database as views: they read
data/parquet/<snapshot_id>/<name>.parquet when it exists and fall back to the snapshot JSONL
otherwise (slow: every query re-parses the file). The sealed snapshot is only read, never
written. Open the database with

    duckdb data/duckdb/group16.duckdb       # CLI
    duckdb -ui data/duckdb/group16.duckdb   # browser UI
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

from .config import (
    AUTHORSHIP_NETWORK,
    CITATION_NETWORK,
    CONFIG,
    DATASET,
    ENRICHED,
    INDIAN_CONNECTIONS,
    METADATA,
    PROCESSED,
    ROOT,
    snapshot_dir,
)

DATABASE = ROOT / "data" / "duckdb" / "group16.duckdb"
PARQUET_ROOT = ROOT / "data" / "parquet"

CSV_TABLES = {
    "data": DATASET,
    "enriched": ENRICHED,
    "authors": PROCESSED / "authors.csv",
    "institutions": METADATA / "institutions.csv",
    "citation_network": CITATION_NETWORK,
    "authorship_network": AUTHORSHIP_NETWORK,
    "indian_connections": INDIAN_CONNECTIONS,
}
RAW_VIEWS = ("works", "authors", "full_authorships", "indian_refs", "indian_citers")


def sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def convert_to_parquet(con: duckdb.DuckDBPyConnection, snapshot_id: str) -> None:
    out_dir = PARQUET_ROOT / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in RAW_VIEWS:
        source = snapshot_dir(snapshot_id) / f"{name}.jsonl"
        target = out_dir / f"{name}.parquet"
        if not source.exists():
            print(f"skip {name}: {source} not found")
            continue
        if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            print(f"skip {name}: Parquet is up to date")
            continue
        start = time.time()
        tmp = target.with_suffix(".parquet.tmp")
        # sample_size=-1 infers the schema from every record, so late fields are not lost.
        con.execute(
            f"COPY (SELECT * FROM read_json_auto({sql_path(source)}, sample_size=-1)) "
            f"TO {sql_path(tmp)} (FORMAT parquet, COMPRESSION zstd)"
        )
        tmp.replace(target)
        size_mb = target.stat().st_size / 1e6
        print(f"{name}: {size_mb:,.0f} MB Parquet in {time.time() - start:,.0f} s")


def load_tables(con: duckdb.DuckDBPyConnection) -> None:
    for name, path in CSV_TABLES.items():
        if not path.exists() or path.stat().st_size == 0:
            print(f"skip table {name}: {path.relative_to(ROOT)} missing or empty")
            continue
        # Drop a view of the same name left by an earlier version of this script.
        is_view = con.execute(
            "SELECT count(*) FROM duckdb_views() WHERE view_name = ? AND NOT internal", [name]
        ).fetchone()[0]
        if is_view:
            con.execute(f"DROP VIEW {name}")
        # sample_size=-1 infers column types from every row; it runs once per load.
        con.execute(
            f"CREATE OR REPLACE TABLE {name} AS "
            f"SELECT * FROM read_csv_auto({sql_path(path)}, sample_size=-1)"
        )
        n_rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        print(f"table {name}: {n_rows:,} rows from {path.relative_to(ROOT)}")


def create_raw_views(con: duckdb.DuckDBPyConnection, snapshot_id: str) -> None:
    for name in RAW_VIEWS:
        view = f"raw_{name}"
        parquet = PARQUET_ROOT / snapshot_id / f"{name}.parquet"
        jsonl = snapshot_dir(snapshot_id) / f"{name}.jsonl"
        if parquet.exists():
            source = f"read_parquet({sql_path(parquet)})"
            path = parquet
        elif jsonl.exists():
            source = f"read_json_auto({sql_path(jsonl)})"
            path = jsonl
        else:
            print(f"skip view {view}: no Parquet or JSONL")
            continue
        con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM {source}")
        print(f"view {view} -> {path.relative_to(ROOT)}")


def main(argv: list[str]) -> None:
    snapshot_id = CONFIG["build"]["snapshot_id"]
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DATABASE)) as con:
        if "--parquet" in argv:
            convert_to_parquet(con, snapshot_id)
        load_tables(con)
        create_raw_views(con, snapshot_id)
    print(f"database: {DATABASE.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
