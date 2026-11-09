"""Ficheros estáticos del INE: diccionario de municipios y cartografía de secciones."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from atlas_spain.http import fetch
from atlas_spain.ingestion.runner import Execution

CODMUN_URL = "https://www.ine.es/daco/daco42/codmun/diccionario{aa}.xlsx"
SECCIONADO_URL = "https://www.ine.es/prodyser/cartografia/seccionado_{aaaa}.zip"


def extract_codmun(ex: Execution, years: list[int] = (2025, 2024, 2023, 2022, 2021, 2020)) -> str | None:
    """Diccionarios anuales de municipios (a 1 de enero). Permite seguir altas/bajas."""
    for y in years:
        aa = f"{y % 100:02d}"
        try:
            r = fetch(CODMUN_URL.format(aa=aa), timeout=90)
        except Exception as exc:
            ex.errors += 1
            ex.error_detail = ((ex.error_detail or "") + f"{y}: {exc}\n")
            continue
        ex.save_raw(f"diccionario{aa}.xlsx", r.content)
        raw = pd.read_excel(io.BytesIO(r.content), header=None, dtype=str)
        # La fila de cabecera contiene CPRO/CMUN; su posición varía entre ediciones.
        hdr = next(i for i in range(10) if "CPRO" in raw.iloc[i].astype(str).str.upper().tolist())
        df = raw.iloc[hdr + 1:].copy()
        df.columns = [str(c).strip().upper() for c in raw.iloc[hdr]]
        df = df.dropna(subset=["CPRO", "CMUN"])
        df["anyo_referencia"] = y
        ex.records_downloaded += len(df)
        ex.save_parquet(f"diccionario_{y}", df)
    return "partial" if ex.errors else None


def extract_seccionado(ex: Execution, years: list[int] = (2024,)) -> str | None:
    """Shapefile de secciones censales → GeoParquet (EPSG:4326) + atributos."""
    import geopandas as gpd

    from atlas_spain import paths

    for y in years:
        # Fichero pesado y servidor lento: se acepta copia previa en landing/ine/.
        local = paths.LANDING / "ine" / f"seccionado_{y}.zip"
        content = local.read_bytes() if local.exists() else \
            fetch(SECCIONADO_URL.format(aaaa=y), timeout=900, retries=2).content
        if not content.startswith(b"PK"):
            raise ValueError(f"seccionado_{y}: no es un ZIP")
        raw_path = ex.save_raw(f"seccionado_{y}.zip", content)
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(raw_path) as zf:
                zf.extractall(tmp)
            shp = sorted(Path(tmp).rglob("*.shp"))
            if not shp:
                raise ValueError(f"seccionado_{y}.zip sin .shp")
            gdf = gpd.read_file(shp[0])
        src_crs = str(gdf.crs)
        gdf = gdf.to_crs(4326)
        gdf.columns = [c.upper() if c != "geometry" else c for c in gdf.columns]
        gdf["ANYO_SECCIONADO"] = y
        gdf["CRS_ORIGEN"] = src_crs
        ex.records_downloaded += len(gdf)
        d = ex.bronze_dir() / "parquet" / f"seccionado_{y}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{ex.execution_id}.parquet"
        gdf["_source_id"], gdf["_execution_id"] = ex.source_id, ex.execution_id
        gdf.to_parquet(p, index=False)   # GeoParquet (geometría WKB + metadatos CRS)
        ex.records_processed += len(gdf)
        from atlas_spain.ingestion.runner import sha256_file
        ex.artifacts.append({"kind": "parquet", "path": str(p), "sha256": sha256_file(p),
                             "bytes": p.stat().st_size, "rows": len(gdf)})
    return None
