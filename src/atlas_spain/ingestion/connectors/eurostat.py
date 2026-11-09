"""Conector Eurostat (API de diseminación, JSON-stat 2.0)."""

from __future__ import annotations

import itertools
import json

import pandas as pd

from atlas_spain.http import fetch
from atlas_spain.ingestion.runner import Execution

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}?format=JSON&lang=EN{params}"

# Filtro a España: códigos NUTS que empiezan por ES. La API acepta geo repetido;
# se pide el dataset con geoLevel y se filtra localmente para no depender de listas.
DATASETS: dict[str, dict] = {
    "EUROSTAT-POP-NUTS3": {"code": "demo_r_pjanaggr3", "params": "&geoLevel=nuts3&sex=T&age=TOTAL"},
    "EUROSTAT-UNEMP-NUTS2": {"code": "lfst_r_lfu3rt", "params": "&geoLevel=nuts2&sex=T&age=Y15-74&isced11=TOTAL"},
    "EUROSTAT-GDP-NUTS3": {"code": "nama_10r_3gdp", "params": "&geoLevel=nuts3"},
}


def jsonstat_to_frame(js: dict) -> pd.DataFrame:
    ids = js["id"]
    dims = js["dimension"]
    cats = []
    for d in ids:
        idx = dims[d]["category"]["index"]
        order = sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)
        cats.append(order)
    values = js.get("value", {})
    status = js.get("status", {})
    rows = []
    for flat, combo in enumerate(itertools.product(*cats)):
        key = str(flat)
        if key not in values and isinstance(values, dict):
            continue
        v = values[key] if isinstance(values, dict) else values[flat]
        rows.append({**dict(zip(ids, combo)), "value": v,
                     "status": status.get(key) if isinstance(status, dict) else None})
    return pd.DataFrame(rows)


def extract(ex: Execution) -> str | None:
    cfg = DATASETS[ex.source_id]
    r = fetch(BASE.format(code=cfg["code"], params=cfg["params"]), timeout=180)
    ex.save_raw(f"{cfg['code']}.json", r.content)
    df = jsonstat_to_frame(json.loads(r.content))
    ex.records_downloaded = len(df)
    df = df[df["geo"].str.startswith("ES")].copy()
    df["dataset"] = cfg["code"]
    ex.save_parquet(cfg["code"], df)
    return None
