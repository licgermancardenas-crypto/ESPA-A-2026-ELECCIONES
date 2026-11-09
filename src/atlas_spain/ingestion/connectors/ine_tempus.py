"""Conector API Tempus3 del INE (servicios.ine.es/wstempus).

Convierte DATOS_TABLA (con tip=AM) a formato largo:
una fila por serie × periodo; cada variable de metadatos se expande a dos
columnas: `<variable>` (nombre) y `<variable>__cod` (código INE).
"""

from __future__ import annotations

import json
import re
import unicodedata

import pandas as pd

from atlas_spain.http import fetch
from atlas_spain.ingestion.runner import Execution

BASE = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{tabla}?nult={nult}&tip=AM"

# source_id -> tablas Tempus. nult = nº de periodos (generoso: trae toda la historia).
TABLES: dict[str, dict] = {
    "INE-DPOP-CCAA": {"tables": [2853], "nult": 60},
    "INE-DPOP-PROV": {"tables": [2852], "nult": 60},
    "INE-DPOP-MUN": {"tables": list(range(2854, 2906)), "nult": 60},
    "INE-OCE": {"tables": [80107], "nult": 20},
    "INE-CRE-PIB": {"tables": [82285, 82284], "nult": 40},
    "INE-EPA-PARO-CCAA": {"tables": [14506], "nult": 120},
    "INE-DIRCE": {"tables": [39374], "nult": 40},
    "INE-IPVA-MUN": {"tables": [59060], "nult": 20},
    "INE-EJEC-HIPOT": {"tables": [10744], "nult": 60},
}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "var"


def tidy(payload: list[dict], tabla: int) -> pd.DataFrame:
    rows = []
    for serie in payload:
        meta = {}
        for m in serie.get("MetaData", []):
            var = slug(m.get("T3_Variable") or m.get("Variable", {}).get("Nombre", "var"))
            meta[var] = m.get("Nombre")
            meta[f"{var}__cod"] = m.get("Codigo")
        for d in serie.get("Data", []):
            rows.append({
                "tabla": tabla,
                "serie_cod": serie.get("COD"),
                "serie_nombre": (serie.get("Nombre") or "").strip(),
                "unidad": serie.get("T3_Unidad"),
                "escala": (serie.get("T3_Escala") or "").strip(),
                "anyo": d.get("Anyo"),
                "fecha": d.get("Fecha"),
                "periodo": d.get("T3_Periodo"),
                "tipo_dato": d.get("T3_TipoDato"),
                "valor": d.get("Valor"),
                "secreto": d.get("Secreto", False),
                **meta,
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"], utc=True, errors="coerce")
    return df


def extract(ex: Execution, source_id: str | None = None, tables: list[int] | None = None) -> str | None:
    cfg = TABLES[source_id or ex.source_id]
    tabs = tables or cfg["tables"]
    frames = []
    for t in tabs:
        try:
            r = fetch(BASE.format(tabla=t, nult=cfg["nult"]), timeout=120)
            ex.save_raw(f"tabla_{t}.json", r.content)
            payload = json.loads(r.content)
            df = tidy(payload, t)
            ex.records_downloaded += len(df)
            frames.append(df)
        except Exception as exc:  # una tabla fallida no tumba el resto
            ex.errors += 1
            ex.error_detail = ((ex.error_detail or "") + f"tabla {t}: {exc}\n")[:4000]
    if not frames:
        return "failed"
    # Tablas con metadatos distintos -> un parquet por tabla (esquemas homogéneos)
    for df in frames:
        ex.save_parquet(f"tabla_{int(df['tabla'].iloc[0])}", df)
    return "partial" if ex.errors else None
