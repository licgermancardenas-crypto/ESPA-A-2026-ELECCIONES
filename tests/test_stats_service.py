"""Integración del servicio estadístico: ámbitos, pesos, períodos, errores y registro de ejecución.

Se usa un panel SINTÉTICO mínimo construido en el test (nunca se mezcla con datos reales) y, si existe,
el panel real exportado del warehouse para comprobar coherencia con cifras oficiales agregadas.
"""

import io
import json

import numpy as np
import pytest

from atlas_spain import paths
from atlas_spain.stats.panel import Panel
from atlas_spain.stats.service import Servicio


def _panel_sintetico(tmp_path):
    # 2 provincias (A: 3 municipios, B: 2), 1 comunidad
    mun = ["ES-MU-01001", "ES-MU-01002", "ES-MU-01003", "ES-MU-02001", "ES-MU-02002"]
    prov = ["ES-PR-01", "ES-PR-01", "ES-PR-01", "ES-PR-02", "ES-PR-02"]
    claves = ["participacion||02-201911", "participacion||02-202307", "censo||02-202307", "poblacion||2025",
              "voto_familia|X|02-202307", "voto_familia|Y|02-202307", "renta_persona||2024"]
    M = np.array([
        [0.70, 0.60, 0.80, 0.50, 0.90],
        [0.72, 0.62, 0.70, 0.55, 0.95],
        [100, 1000, 10, 500, 50],
        [120, 1200, 12, 600, 60],
        [0.6, 0.3, 0.5, 0.2, 0.7],
        [0.4, 0.7, 0.5, 0.8, 0.3],
        [10000, 12000, np.nan, 9000, 15000],
    ], np.float32)
    meta = {"catalogo": [{"variable": v, "nombre": v, "unidad": "proporción"} for v in ("participacion", "censo", "poblacion", "voto_familia", "renta_persona")],
            "niveles": {"municipio": {"ids": mun, "nombres": ["a1", "a2", "a3", "b1", "b2"], "provincia": prov, "ccaa": ["ES-CA-01"] * 5, "claves": claves},
                        "provincia": {"ids": ["ES-PR-01", "ES-PR-02"], "nombres": ["A", "B"], "provincia": ["ES-PR-01", "ES-PR-02"], "ccaa": ["ES-CA-01"] * 2, "claves": []},
                        "ccaa": {"ids": ["ES-CA-01"], "nombres": ["C"], "provincia": [None], "ccaa": ["ES-CA-01"], "claves": []},
                        "pais": {"ids": ["ES"], "nombres": ["España"], "provincia": [None], "ccaa": [None], "claves": []}}}
    vec = [[1, 3], [0, 2], [1], [0, 4], [3]]
    buf = io.BytesIO()
    np.savez_compressed(buf, meta=np.frombuffer(json.dumps(meta).encode(), np.uint8),
                        municipio__M=M, provincia__M=np.zeros((0, 2), np.float32), ccaa__M=np.zeros((0, 1), np.float32),
                        pais__M=np.zeros((0, 1), np.float32),
                        municipio__vec_n=np.array([len(v) for v in vec], np.int32), municipio__vec=np.array([j for v in vec for j in v], np.int32))
    f = tmp_path / "sintetico.npz"
    f.write_bytes(buf.getvalue())
    return Panel(f)


@pytest.fixture
def servicio(tmp_path):
    registro = []
    s = Servicio(_panel_sintetico(tmp_path), registro=registro.append)
    s._registro = registro
    return s


def test_media_ponderada_por_censo_es_el_agregado(servicio):
    r = servicio.ejecutar("descriptiva", {"x": {"variable": "participacion", "periodo": "02-202307"}, "peso": "censo"})["resultado"]
    w = np.array([100, 1000, 10, 500, 50]); x = np.array([0.72, 0.62, 0.70, 0.55, 0.95])
    assert r["media_ponderada"] == pytest.approx((w * x).sum() / w.sum(), rel=1e-6)
    assert r["media"] == pytest.approx(x.mean(), rel=1e-6)


def test_ambito_provincia_filtra(servicio):
    r = servicio.ejecutar("descriptiva", {"x": {"variable": "participacion", "periodo": "02-202307"}, "ambito": {"dentro": "ES-PR-02"}})["resultado"]
    assert r["n"] == 2 and r["media"] == pytest.approx(0.75, rel=1e-6)


def test_filtro_poblacion_minima(servicio):
    r = servicio.ejecutar("descriptiva", {"x": {"variable": "participacion", "periodo": "02-202307"}, "ambito": {"min_poblacion": 100}})["resultado"]
    assert r["n"] == 3  # 120, 1200 y 600 habitantes


def test_cambio_entre_periodos(servicio):
    r = servicio.ejecutar("descriptiva", {"x": {"variable": "participacion", "periodo": "02-202307", "base": "02-201911"}})["resultado"]
    assert r["maximo"] == pytest.approx(0.05, abs=1e-6) and r["minimo"] == pytest.approx(-0.10, abs=1e-6)


def test_faltantes_se_informan(servicio):
    r = servicio.ejecutar("descriptiva", {"x": {"variable": "renta_persona", "periodo": "2024"}})
    assert r["resultado"]["n"] == 4 and r["resultado"]["n_faltantes"] == 1


def test_ganador_categorico_y_contingencia(servicio):
    r = servicio.ejecutar("probabilidad", {"a": {"variable": "participacion", "periodo": "02-202307", "cuantiles": 2},
                                           "b": {"variable": "ganador", "periodo": "02-202307"}})["resultado"]
    assert r["n"] == 5 and set(r["columnas"]) <= {"X", "Y"}
    assert sum(r["denominadores"]["filas"]) == 5


def test_errores_de_peticion_no_rompen(servicio):
    for metodo, params in (("descriptiva", {"x": {"variable": "inventada", "periodo": "2024"}}),
                           ("descriptiva", {"x": {"variable": "participacion", "periodo": "02-209901"}}),
                           ("descriptiva", {"x": {"variable": "participacion", "periodo": "02-202307"}, "ambito": {"dentro": "XX"}}),
                           ("descriptiva", {"x": {"variable": "renta_persona", "periodo": "2024"}, "peso": "censo"}),
                           ("inexistente", {})):
        r = servicio.ejecutar(metodo, params)
        assert r["error"] and r["ejecucion"]["estado"] == "error_peticion", (metodo, params)


def test_registro_de_ejecucion(servicio):
    r = servicio.ejecutar("correlacion", {"x": {"variable": "participacion", "periodo": "02-201911"}, "y": {"variable": "participacion", "periodo": "02-202307"}})
    e = r["ejecucion"]
    assert e["metodo"] == "correlacion" and e["panel"] == servicio.P.huella and e["version_motor"] and e["parametros"]
    assert servicio._registro and servicio._registro[-1]["run_id"] == e["run_id"]
    json.dumps(r, allow_nan=False)  # respuesta serializable sin NaN


def test_contraste_pareado(servicio):
    r = servicio.ejecutar("contraste", {"x": {"variable": "participacion"}, "periodos": ["02-201911", "02-202307"]})["resultado"]
    assert r["n"] == 5 and r["diferencia_media"] == pytest.approx(np.mean([0.02, 0.02, -0.10, 0.05, 0.05]), abs=1e-6)


def test_espacial_con_vecinos(servicio):
    r = servicio.ejecutar("espacial", {"x": {"variable": "participacion", "periodo": "02-202307"}, "permutaciones": 9})
    assert r["ejecucion"]["estado"] == "ok"  # con n < 10 devuelve aviso, no error


# ─────────── panel real (si está exportado) ───────────
REAL = paths.DATA / "gold" / "stat_panel.npz"


@pytest.mark.skipif(not REAL.exists(), reason="panel real no exportado")
def test_real_participacion_agregada_coincide_con_sumas_oficiales():
    import duckdb
    s = Servicio(Panel(REAL))
    r = s.ejecutar("descriptiva", {"x": {"variable": "participacion", "periodo": "02-202307"}, "peso": "censo"})["resultado"]
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    v, c = con.execute("""select sum(votantes), sum(censo) from gold.fact_turnout t
                          join gold.dim_geography g on g.geo_id = t.geo_id
                          where t.election_id = '02-202307' and t.geo_level = 'municipio'""").fetchone()
    assert r["media_ponderada"] == pytest.approx(v / c, abs=1e-4)


@pytest.mark.skipif(not REAL.exists(), reason="panel real no exportado")
def test_real_cobertura_geografica():
    p = Panel(REAL)
    assert len(p.nivel("municipio")["ids"]) == 8132 and len(p.nivel("provincia")["ids"]) == 52
    assert sum(1 for v in p.vecinos["municipio"] if v) > 8100
