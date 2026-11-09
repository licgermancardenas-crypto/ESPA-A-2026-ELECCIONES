"""Orquestador del warehouse: geo → dbt (silver/gold) → controles post-build.

Detecta qué datasets bronze existen y activa solo los modelos que tienen datos,
para no fabricar tablas vacías que parezcan completas.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import yaml

from atlas_spain import paths

DBT_DIR = paths.ROOT / "dbt"


def _has(source_glob: str, dataset_glob: str) -> bool:
    return any(paths.BRONZE.glob(f"{source_glob}/parquet/{dataset_glob}/*.parquet"))


def write_election_dates_seed() -> None:
    with open(paths.CONFIG / "elections.yaml", encoding="utf-8") as f:
        fechas = yaml.safe_load(f).get("fechas", {})
    lines = ["election_id,fecha"] + [f"{k},{v}" for k, v in sorted(fechas.items())]
    (DBT_DIR / "seeds" / "election_dates.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_dbt(args: list[str], dbt_vars: dict) -> int:
    env = {**os.environ, "ATLAS_WAREHOUSE": str(paths.WAREHOUSE).replace("\\", "/"),
           "DBT_PROFILES_DIR": str(DBT_DIR)}
    cmd = ["dbt", *args, "--project-dir", str(DBT_DIR), "--vars", json.dumps(dbt_vars)]
    print("$", " ".join(cmd[:2]), "…")
    return subprocess.run(cmd, cwd=DBT_DIR, env=env).returncode


def main(skip_geo: bool = False) -> int:
    paths.ensure_dirs()
    dbt_vars = {
        "bronze_root": str(paths.BRONZE).replace("\\", "/"),
        "registry_csv": str(paths.ROOT / "DATA_SOURCE_REGISTRY.csv").replace("\\", "/"),
        "has_infoelectoral": _has("MIR-IE-*", "f07_*") and _has("MIR-IE-*", "f05_*"),
        "has_seccionado": _has("INE-SECCIONADO", "seccionado_*"),
        "has_euskadi": _has("EUSKADI-ELEC", "*"),
    }
    print("Datasets presentes:", {k: v for k, v in dbt_vars.items() if k.startswith("has_")})

    if dbt_vars["has_seccionado"] and not skip_geo:
        from atlas_spain.geo.build_geo import build as build_geo
        print("Geo:", build_geo())

    write_election_dates_seed()
    for step in (["seed"], ["run"], ["test"]):
        rc = run_dbt(step, dbt_vars)
        if rc != 0:
            print(f"dbt {step[0]} terminó con código {rc}", file=sys.stderr)
            return rc

    from atlas_spain.quality import checks
    return checks.main()
