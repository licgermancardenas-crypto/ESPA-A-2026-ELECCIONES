"""Rutas del proyecto. Todo el almacenamiento vive bajo data/ (fuera de git)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("ATLAS_ROOT", Path(__file__).resolve().parents[2]))
CONFIG = ROOT / "config"
DATA = Path(os.environ.get("ATLAS_DATA", ROOT / "data"))

LANDING = DATA / "landing"      # ficheros dejados a mano (fuentes con anti-bot o formularios)
BRONZE = DATA / "bronze"        # ficheros originales + parquet "tal cual" por ejecución
WAREHOUSE_DIR = DATA / "warehouse"
WAREHOUSE = WAREHOUSE_DIR / "atlas.duckdb"
OPS = DATA / "ops"              # log de ejecuciones en JSONL (además de la tabla ops.executions)


def ensure_dirs() -> None:
    for p in (LANDING, BRONZE, WAREHOUSE_DIR, OPS):
        p.mkdir(parents=True, exist_ok=True)
