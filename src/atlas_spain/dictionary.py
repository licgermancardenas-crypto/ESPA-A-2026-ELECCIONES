"""Genera DATA_DICTIONARY.md a partir del warehouse REAL (information_schema)
más las descripciones mantenidas aquí. Tablas sin descripción se listan igual."""

from __future__ import annotations

from atlas_spain import paths
from atlas_spain.warehouse import connect

TABLES = {
    "gold.dim_geography": "Registro geográfico maestro: país, CCAA, provincias, municipios, distritos y secciones.",
    "gold.geo_boundaries": "Geometrías simplificadas (WKB, EPSG:4326) por geo_id y año del seccionado.",
    "gold.fact_population": "Cifras oficiales de población del Padrón (1 de enero) por territorio, año y sexo.",
    "gold.fact_economy_province": "PIB y PIB per cápita (Contabilidad Regional del INE) por provincia, CCAA y total.",
    "gold.dim_data_source": "Catálogo de fuentes con estado verificado en vivo.",
    "gold.dim_election": "Convocatorias electorales cargadas.",
    "gold.fact_turnout": "Censo, votantes, blancos, nulos y participación por convocatoria y territorio.",
    "gold.fact_election_results": "Votos, escaños y cuotas por candidatura, convocatoria y territorio.",
    "gold.election_indices": "ENEP, ENPP, Gallagher, margen, competitividad y dominio por convocatoria y territorio.",
    "silver.ref_ccaa": "Comunidades y ciudades autónomas (código INE).",
    "silver.ref_provincia": "Provincias con su comunidad autónoma.",
    "silver.dim_municipality": "Municipios con vigencia observada en diccionarios anuales.",
    "silver.fact_population": "Población normalizada (antes de enriquecer con nombres).",
    "silver.geo_census_units": "Distritos y secciones censales con jerarquía.",
    "silver.xw_ccaa_mir_ine": "Equivalencia de códigos de CCAA Ministerio del Interior → INE (derivada de datos).",
    "ops.executions": "Log de ejecuciones de ingesta (Data Operations Center).",
    "ops.artifacts": "Ficheros escritos por cada ejecución, con hash SHA-256.",
    "ops.quality_results": "Resultados de los controles de calidad por run.",
}

COLUMNS = {
    "geo_id": "Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1).",
    "geo_type": "pais | ccaa | provincia | municipio | distrito | seccion.",
    "parent_geo_id": "geo_id del nivel superior.",
    "official_code": "Código oficial INE del territorio.",
    "valid_from": "Inicio de vigencia observado; nulo = anterior a la cobertura descargada.",
    "valid_to": "Fin de vigencia; nulo = vigente en el último dato.",
    "source_id": "Fuente en DATA_SOURCE_REGISTRY.",
    "anyo": "Año de referencia (Padrón: población a 1 de enero de ese año).",
    "sexo": "T total, H hombres, M mujeres.",
    "poblacion": "Personas empadronadas (cifra oficial).",
    "tipo_dato": "Estado del dato según el INE (Definitivo, Provisional, Avance…).",
    "_execution_id": "Ejecución de ingesta que produjo la fila (linaje).",
    "election_id": "{tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas.",
    "candidacy_id": "Candidatura dentro de una convocatoria ({election_id}-{código}). No es un partido.",
    "censo": "Censo electoral de escrutinio (incluye CERA en ámbitos supramunicipales).",
    "votantes": "Blancos + nulos + votos a candidaturas.",
    "votos_validos": "Blancos + votos a candidaturas.",
    "turnout": "Votantes / censo.",
    "vote_share": "Votos / votos a candidaturas.",
    "share_valid": "Votos / votos válidos.",
    "incluye_cera": "Si el ámbito incluye el voto de residentes ausentes.",
    "enep": "Número efectivo de partidos electorales (Laakso–Taagepera).",
    "enpp": "Número efectivo de partidos parlamentarios.",
    "gallagher": "Índice de desproporcionalidad de Gallagher (puntos %).",
    "area_km2": "Área calculada en EPSG:3035 sobre la geometría completa.",
    "geometry_wkb": "Geometría simplificada en WKB (EPSG:4326).",
}


def main() -> int:
    con = connect(read_only=True)
    try:
        cols = con.execute("""select table_schema, table_name, column_name, data_type
            from information_schema.columns where table_schema in ('silver','gold','ops')
            order by table_schema, table_name, ordinal_position""").fetchall()
        counts = {f"{s}.{t}": n for s, t, n in con.execute(
            "select schema_name, table_name, estimated_size from duckdb_tables()").fetchall()}
    finally:
        con.close()
    by_table: dict[str, list] = {}
    for s, t, c, dt in cols:
        by_table.setdefault(f"{s}.{t}", []).append((c, dt))
    out = ["# DATA DICTIONARY — ATLAS SPAIN", "",
           "Generado automáticamente desde el warehouse (`python -m atlas_spain.dictionary`). "
           "No editar a mano: las descripciones viven en `src/atlas_spain/dictionary.py`.", "",
           "Columnas de linaje presentes en bronze/silver: `_source_id`, `_execution_id`, `_ingested_at`.", ""]
    for name in sorted(by_table, key=lambda n: (["gold", "silver", "ops"].index(n.split(".")[0]), n)):
        if name.startswith("silver.stg_"):
            continue
        rows = counts.get(name)
        out += [f"## `{name}`", "", TABLES.get(name, "_Sin descripción._"),
                "" if rows is None else f"\nFilas (estimadas): {rows:,}".replace(",", "."), "",
                "| Columna | Tipo | Descripción |", "|---|---|---|"]
        out += [f"| `{c}` | {dt} | {COLUMNS.get(c, '')} |" for c, dt in by_table[name]]
        out.append("")
    (paths.ROOT / "DATA_DICTIONARY.md").write_text("\n".join(out), encoding="utf-8")
    print(f"DATA_DICTIONARY.md: {len(by_table)} tablas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
