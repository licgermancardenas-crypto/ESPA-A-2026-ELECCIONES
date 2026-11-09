import pytest
from fastapi import HTTPException

from atlas_spain.api.main import validate_select
from atlas_spain.http import looks_like_challenge
from atlas_spain.ingestion.connectors.eurostat import jsonstat_to_frame
from atlas_spain.ingestion.connectors.ine_tempus import slug, tidy
from atlas_spain.registry import load_sources


def test_jsonstat_aplanado():
    js = {"id": ["geo", "time"], "size": [2, 2],
          "dimension": {"geo": {"category": {"index": {"ES30": 0, "ES51": 1}}},
                        "time": {"category": {"index": {"2022": 0, "2023": 1}}}},
          "value": {"0": 1.0, "1": 2.0, "3": 4.0}}
    df = jsonstat_to_frame(js)
    assert len(df) == 3  # la celda 2 no existe (dato ausente), no se inventa
    assert df.loc[(df.geo == "ES51") & (df.time == "2023"), "value"].item() == 4.0


def test_ine_tidy_metadatos():
    payload = [{"COD": "X1", "Nombre": "Madrid. Total.", "T3_Unidad": "Personas", "T3_Escala": " ",
                "MetaData": [{"Codigo": "28079", "Nombre": "Madrid", "T3_Variable": "Municipios"},
                             {"Codigo": "0", "Nombre": "Total", "T3_Variable": "Sexo"}],
                "Data": [{"Anyo": 2024, "Fecha": "2024-01-01T00:00:00.000+01:00", "T3_Periodo": "A",
                          "T3_TipoDato": "Definitivo", "Valor": 3.4e6}]}]
    df = tidy(payload, 2881)
    assert df.loc[0, "municipios__cod"] == "28079" and df.loc[0, "sexo"] == "Total"
    assert slug("Tamaño de los municipios") == "tamano_de_los_municipios"


def test_deteccion_desafio_antibot():
    assert looks_like_challenge(403, "text/html; charset=UTF-8", b"<title>Just a moment...</title>")
    assert not looks_like_challenge(200, "application/zip", b"PK\x03\x04")
    assert not looks_like_challenge(403, "text/html", b"<h1>Access Denied</h1>")


def test_registro_minimo_40_fuentes_y_campos():
    src = load_sources()
    assert len(src) >= 40
    required = {"source_id", "organismo", "dataset", "categoria", "url", "formato", "cobertura_territorial",
                "cobertura_historica", "frecuencia", "granularidad", "licencia", "metodo_extraccion", "probe_url"}
    for s in src:
        assert required <= set(s), s["source_id"]


@pytest.mark.parametrize("sql", [
    "select 1",
    "with a as (select 1 x) select * from a",
])
def test_sql_explorer_acepta_select(sql):
    validate_select(sql)


@pytest.mark.parametrize("sql", [
    "drop table gold.dim_geography",
    "select 1; select 2",
    "insert into ops.executions values (1)",
    "select * from read_csv('C:/secretos.csv')",
    "attach 'x.db'",
    "copy (select 1) to 'x.csv'",
])
def test_sql_explorer_rechaza(sql):
    with pytest.raises(HTTPException):
        validate_select(sql)
