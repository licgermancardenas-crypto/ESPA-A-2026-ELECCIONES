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
    # Una tabla por provincia; los IDs NO son correlativos -> se resuelven del catálogo.
    "INE-DPOP-MUN": {"operation": 22, "name_contains": "Población por municipios y sexo", "nult": 60},
    "INE-CRE-PIB": {"tables": [82285, 82284], "nult": 40},
    "INE-EPA-PARO-CCAA": {"tables": [14506], "nult": 120},
    "INE-DIRCE": {"tables": [39374], "nult": 40},
    "INE-IPVA-MUN": {"tables": [59060], "nult": 20},
    "INE-EJEC-HIPOT": {"tables": [10744], "nult": 60},
    # Atlas de Renta: una tabla por provincia; la API exige filtrar el indicador (tv=variable:valor)
    # para no superar el límite de volumen. Último año publicado (nult=1).
    "INE-ADRH": {"operation": 353, "nult": 1, "queries": [
        ("Indicadores de renta media y mediana", "482:284048"),   # renta neta media por persona
        ("Indicadores demográficos", "260:17338"),               # población
        ("Indicadores demográficos", "260:366831"),              # % población de 65 y más años
    ]},
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


# Tablas demasiado grandes para la API ("restricciones de volumen"): descarga CSV oficial.
CSV_TABLES: dict[str, list[int]] = {"INE-OCE": [80107]}
CSV_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bdsc/{tabla}.csv"
OPS_URL = "https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/{op}"


def resolve_tables(cfg: dict) -> list:
    """Lista de (tabla, filtro_tv | None)."""
    if "tables" in cfg:
        return [(t, None) for t in cfg["tables"]]
    cat = json.loads(fetch(OPS_URL.format(op=cfg["operation"]), timeout=60).content)
    queries = cfg.get("queries") or [(cfg["name_contains"], None)]
    out = []
    for nombre, tv in queries:
        out += [(int(t["Id"]), tv) for t in cat if t["Nombre"].lower().startswith(nombre.lower())]
    return sorted(out, key=lambda x: (x[0], x[1] or ""))


def extract(ex: Execution, source_id: str | None = None, tables: list[int] | None = None) -> str | None:
    cfg = TABLES[source_id or ex.source_id]
    tabs = [(t, None) for t in tables] if tables else resolve_tables(cfg)
    frames = []
    for t, tv in tabs:
        try:
            url = BASE.format(tabla=t, nult=cfg["nult"]) + (f"&tv={tv}" if tv else "")
            r = fetch(url, timeout=300)
            payload = json.loads(r.content)
            if isinstance(payload, dict):
                raise ValueError(f"API: {payload.get('status')}")
            ex.save_raw(f"tabla_{t}{'_' + tv.replace(':', '-') if tv else ''}.json", r.content)
            df = tidy(payload, t)
            df["filtro_tv"] = tv
            ex.records_downloaded += len(df)
            frames.append(df)
        except Exception as exc:  # una tabla fallida no tumba el resto
            ex.errors += 1
            ex.error_detail = ((ex.error_detail or "") + f"tabla {t}: {exc}\n")[:4000]
    if not frames:
        return "failed"
    # Tablas con metadatos distintos -> un parquet por tabla (esquemas homogéneos)
    for df in frames:
        tv = df["filtro_tv"].iloc[0]
        ex.save_parquet(f"tabla_{int(df['tabla'].iloc[0])}" + (f"_{tv.replace(':', '-')}" if tv else ""), df)
    return "partial" if ex.errors else None


_CODE_NAME = re.compile(r"^(\d{2,5})\s+(.*)$")


def extract_csv(ex: Execution) -> str | None:
    """CSV 'bdsc' del INE: separador ';', miles con '.', decimales con ','.
    Las columnas territoriales vienen como '28079 Madrid' -> se separan código y nombre."""
    import io
    for t in CSV_TABLES[ex.source_id]:
        r = fetch(CSV_URL.format(tabla=t), timeout=600)
        ex.save_raw(f"tabla_{t}.csv", r.content)
        df = pd.read_csv(io.BytesIO(r.content), sep=";", dtype=str, encoding="utf-8-sig")
        ex.records_downloaded += len(df)
        df.columns = [slug(c) for c in df.columns]
        for c in list(df.columns):
            if c in ("total", "periodo"):
                continue
            ext = df[c].str.extract(_CODE_NAME)
            if ext[0].notna().any():
                df[f"{c}__cod"] = ext[0]
                df[c] = ext[1].where(ext[0].notna(), df[c])
        df["valor"] = pd.to_numeric(df.pop("total").str.replace(".", "", regex=False)
                                    .str.replace(",", ".", regex=False), errors="coerce")
        df["tabla"] = t
        ex.save_parquet(f"tabla_{t}", df)
    return None
