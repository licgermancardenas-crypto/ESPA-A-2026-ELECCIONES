"""Conexión al warehouse DuckDB (bronze / silver / gold / ops)."""

from __future__ import annotations

import duckdb

from atlas_spain import paths

SCHEMAS = ("bronze", "silver", "gold", "ops", "ref")

# Máquina de referencia con ~3,4 GB de RAM: límites conservadores.
MEMORY_LIMIT = "1GB"
THREADS = 2


def connect(read_only: bool = False, path=None) -> duckdb.DuckDBPyConnection:
    paths.ensure_dirs()
    db = path or paths.WAREHOUSE
    con = duckdb.connect(str(db), read_only=read_only)
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={THREADS}")
    if not read_only:
        for s in SCHEMAS:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    return con
