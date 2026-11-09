"""Motor geoespacial: del seccionado del INE al registro geográfico y a las capas web.

Entrada : bronze INE-SECCIONADO (GeoParquet, EPSG:4326, una fila por sección).
Salidas :
  silver.geo_census_units   distritos y secciones (atributos + jerarquía)
  gold.geo_boundaries       geometría simplificada (WKB) por geo_id, con área y centroide
  data/gold/geo/*.geojson   capas para MapLibre (simplificadas, topología compartida)
  data/gold/geo/secciones_{AAAA}.parquet  GeoParquet a resolución completa

Notas:
- Las secciones cambian cada año. La geometría es la vigente a 1 de enero del
  año del seccionado; no se asume correspondencia con años anteriores.
- Municipios, provincias y CCAA se obtienen disolviendo secciones: los límites
  coinciden con la cartografía censal, no con las líneas límite jurisdiccionales
  del IGN (CNIG-LINEAS-LIMITE), que son la referencia legal.
- No existen geometrías oficiales de mesas electorales: no se generan.
"""

from __future__ import annotations

import glob

import geopandas as gpd
import pandas as pd
import shapely

from atlas_spain import paths
from atlas_spain.warehouse import connect

LAEA = 3035                      # proyección equivalente europea para áreas
SIMPLIFY = {"seccion": 0.0002, "distrito": 0.0004, "municipio": 0.0008,
            "provincia": 0.003, "ccaa": 0.005}   # grados (≈ 20 m … 500 m)


def _latest_seccionado() -> tuple[gpd.GeoDataFrame, int]:
    files = sorted(glob.glob(str(paths.BRONZE / "INE-SECCIONADO" / "parquet" / "seccionado_*" / "*.parquet")))
    if not files:
        raise FileNotFoundError("No hay seccionado en bronze: ejecutar `atlas ingest INE-SECCIONADO`")
    frames = [gpd.read_parquet(f) for f in files]
    latest = max(frames, key=lambda g: (int(g["ANYO_SECCIONADO"].iloc[0]), str(g["_execution_id"].iloc[0])))
    return latest, int(latest["ANYO_SECCIONADO"].iloc[0])


def _dissolve(gdf: gpd.GeoDataFrame, key: str) -> gpd.GeoDataFrame:
    """Unión por grupos. El seccionado es una cobertura (sin solapes), así que
    coverage_union_all es órdenes de magnitud más rápido que unary_union."""
    keys, geoms = [], []
    for k, grp in gdf.groupby(key, sort=True):
        g = grp.geometry.values
        try:
            u = shapely.coverage_union_all(g)
        except Exception:
            u = shapely.union_all(g)
        keys.append(k)
        geoms.append(shapely.make_valid(u))
    return gpd.GeoDataFrame({key: keys}, geometry=geoms, crs=gdf.crs)


def _simplify_coverage(gdf: gpd.GeoDataFrame, tol: float) -> gpd.GeoSeries:
    try:
        geoms = shapely.coverage_simplify(gdf.geometry.values, tolerance=tol, simplify_boundary=True)
    except Exception:  # cobertura no válida -> simplificación por geometría
        geoms = shapely.simplify(gdf.geometry.values, tol, preserve_topology=True)
    return gpd.GeoSeries(geoms, crs=gdf.crs)


def build() -> dict:
    sec, year = _latest_seccionado()
    sec = sec.set_geometry("geometry")
    vf = pd.Timestamp(year=year, month=1, day=1).date()

    # ── atributos: distritos y secciones ──
    units = pd.concat([
        pd.DataFrame({"geo_id": "ES-DI-" + sec["CUDIS"], "geo_type": "distrito",
                      "geo_name": sec["NMUN"] + " — distrito " + sec["CDIS"],
                      "parent_geo_id": "ES-MU-" + sec["CUMUN"], "official_code": sec["CUDIS"]}).drop_duplicates("geo_id"),
        pd.DataFrame({"geo_id": "ES-SE-" + sec["CUSEC"], "geo_type": "seccion",
                      "geo_name": sec["NMUN"] + " — sección " + sec["CDIS"] + "-" + sec["CSEC"],
                      "parent_geo_id": "ES-DI-" + sec["CUDIS"], "official_code": sec["CUSEC"]}),
    ], ignore_index=True)
    units["valid_from"] = vf
    units["valid_to"] = pd.NaT
    units["source_id"] = "INE-SECCIONADO"
    units["anyo_seccionado"] = year

    # ── geometrías por nivel ──
    levels = {
        "seccion": ("CUSEC", "ES-SE-"), "distrito": ("CUDIS", "ES-DI-"),
        "municipio": ("CUMUN", "ES-MU-"), "provincia": ("CPRO", "ES-PR-"), "ccaa": ("CCA", "ES-CA-"),
    }
    out_dir = paths.DATA / "gold" / "geo"
    out_dir.mkdir(parents=True, exist_ok=True)
    sec[["CUSEC", "CUDIS", "CUMUN", "CPRO", "CCA", "NMUN", "geometry"]].to_parquet(
        out_dir / f"secciones_{year}.parquet", index=False)

    boundary_frames = []
    for level, (key, prefix) in levels.items():
        g = sec[[key, "geometry"]].copy() if level == "seccion" else _dissolve(sec, key)
        area = g.to_crs(LAEA).area / 1e6
        simp = _simplify_coverage(g, SIMPLIFY[level])
        cen = g.to_crs(LAEA).representative_point().to_crs(4326)
        bf = pd.DataFrame({
            "geo_id": prefix + g[key].values, "geo_type": level, "anyo_geometria": year,
            "area_km2": area.round(4).values, "lon": cen.x.round(6).values, "lat": cen.y.round(6).values,
            "geometry_wkb": shapely.to_wkb(simp.values),
        })
        boundary_frames.append(bf)
        if level != "seccion":   # secciones: demasiado pesadas para un GeoJSON único
            gj = gpd.GeoDataFrame({"geo_id": bf["geo_id"], "area_km2": bf["area_km2"]}, geometry=simp.values, crs=4326)
            gj.to_file(out_dir / f"{level}_{year}.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    boundaries = pd.concat(boundary_frames, ignore_index=True)

    con = connect()
    try:
        con.register("units_df", units)
        con.execute("CREATE OR REPLACE TABLE silver.geo_census_units AS SELECT * FROM units_df")
        con.register("b_df", boundaries)
        con.execute("CREATE OR REPLACE TABLE gold.geo_boundaries AS SELECT * FROM b_df")
    finally:
        con.close()
    return {"anyo": year, "secciones": int((units.geo_type == "seccion").sum()),
            "distritos": int((units.geo_type == "distrito").sum()),
            "geometrias": len(boundaries)}
