#!/usr/bin/env bash
# Open the DuckDB browser UI on data/duckdb/group16.duckdb (read-only).
# Create the database first: PYTHONPATH=src .venv/bin/python -m dpcn_mapping.duckdb_setup
#
# OPENSSL_CONF=/dev/null: the UI extension bundles its own OpenSSL, which cannot load
# Fedora's /etc/ssl/openssl.cnf (crypto-policies include), so every fetch from
# https://ui.duckdb.org fails with "SSL connection failed". Skipping the config fixes it.
set -euo pipefail
cd "$(dirname "$0")/.."

#
# The main connection stays writable (in memory) so the UI can create its own state
# database (~/.duckdb/extension_data/ui/ui.db); only group16.duckdb is attached read-only.
OPENSSL_CONF=/dev/null exec .venv/bin/python -c '
import threading
import duckdb
con = duckdb.connect()
con.sql("ATTACH '\''data/duckdb/group16.duckdb'\'' AS group16 (READ_ONLY)")
con.sql("USE group16")
con.sql("CALL start_ui()")
print("DuckDB UI at http://localhost:4213 - press Ctrl+C to stop", flush=True)
try:
    threading.Event().wait()
except KeyboardInterrupt:
    print("stopped")
'
