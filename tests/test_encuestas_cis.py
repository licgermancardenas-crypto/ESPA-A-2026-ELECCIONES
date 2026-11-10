"""Microdatos del CIS: lector de sintaxis SPSS, clasificación en familias y métodos de votantes."""

import numpy as np
import pytest

from atlas_spain import paths
from atlas_spain.encuestas import cis


def test_familias_desde_etiquetas_del_cis():
    casos = {"PSOE": "PSOE", "PP": "PP", "VOX": "Vox", "Sumar": "Sumar", "Unidas Podemos": "Podemos y confluencias",
             "En Comú Podem": "Podemos y confluencias", "C's": "Ciudadanos", "JxCat": "Convergència / Junts", "CDC": "Convergència / Junts",
             "EAJ-PNV": "PNV", "Més Compromís": "Compromís", "Compromís-Podemos-EUPV": "Podemos y confluencias", "Na+": "NA+ (coalición UPN-PP-Cs)",
             "No votó": "Abstención", "Abstención": "Abstención", "En blanco": "Blanco o nulo", "Voto nulo": "Blanco o nulo",
             "No tenía edad": "Nuevos votantes", "No recuerda": None, "N.C.": None, "No tenía derecho a voto": None, "Otros partidos": "Otros"}
    for etiqueta, esperado in casos.items():
        assert cis.familia(etiqueta) == esperado, etiqueta


def test_lector_de_sintaxis_spss(tmp_path):
    es = tmp_path / "ES0001"
    da = tmp_path / "DA0001"
    es.write_bytes("""DATA LIST FILE= 'DA0001'
/SEXO 1 EDAD 2-3 PESO 4-10(5) RECUERDO 11-12
.
VALUE LABELS
/SEXO
1 'Hombre' 2 'Mujer'
/RECUERDO
1 'PP' 2 'PSOE' 4 'C''s' 97 'No votó'
""".encode("latin-1"))
    da.write_bytes("1451,4927401\n2300,8000097\n".encode("latin-1"))
    df, lab = cis.leer_sintaxis(es, da, ["SEXO", "EDAD", "PESO", "RECUERDO"])
    assert df.EDAD.tolist() == [45, 30]
    assert df.PESO.tolist() == pytest.approx([1.49274, 0.8])   # coma decimal y decimales implícitos
    assert lab["RECUERDO"][4.0] == "C's" and lab["SEXO"][2.0] == "Mujer"


PANEL = paths.DATA / "gold" / "stat_panel.npz"


@pytest.fixture(scope="module")
def servicio():
    if not PANEL.exists():
        pytest.skip("panel real no exportado")
    from atlas_spain.stats.panel import Panel
    from atlas_spain.stats.service import Servicio
    s = Servicio(Panel(PANEL))
    if s.P.encuesta is None:
        pytest.skip("microdatos del CIS no integrados")
    return s


def test_ajuste_reproduce_resultado_oficial(servicio):
    d, _, _ = servicio._encuesta("02-202307")
    w, info = servicio._pesos(d, "02-202307", "resultado_oficial")
    partido = np.array([v is not None and v not in servicio._NO_PARTIDO for v in d["voto"]])
    tot = w[partido].sum()
    for fam in ("PP", "PSOE", "Vox", "Sumar"):
        decl = w[partido & (d["voto"] == fam)].sum() / tot
        ofi = servicio.P.serie("pais", "voto_familia", "02-202307", fam)[0]
        assert decl == pytest.approx(ofi, abs=1e-6)


def test_perfil_filas_suman_uno_e_ic_contienen_estimacion(servicio):
    r = servicio.ejecutar("votantes", {"vista": "perfil", "dimension": "grupo_edad"})
    assert r["error"] is None
    for f in r["resultado"]["tabla"]:
        ps = [c["p"] for c in f["celdas"] if c]
        assert sum(ps) == pytest.approx(1, abs=1e-6)
        for c in f["celdas"]:
            if c:
                assert c["ic"][0] <= c["p"] <= c["ic"][1] and c["n_ef"] <= c["n"] + 1e-9


def test_trasvases_coherentes(servicio):
    d = servicio.ejecutar("trasvases", {"eleccion": "02-202307"})["resultado"]
    M = np.array(d["destino_de_origen"])
    assert np.allclose(M.sum(1), 1) and np.array(d["flujo"]).sum() <= 1 + 1e-9
    assert "Nuevos votantes" in d["origen"]


def test_validacion_y_eleccion_inexistente(servicio):
    v = servicio.ejecutar("validacion_cis", {})["resultado"]["convocatorias"]
    assert len(v) == 5 and all(c["participacion_declarada"] > c["participacion_oficial"] for c in v)
    assert servicio.ejecutar("votantes", {"eleccion": "02-200803"})["ejecucion"]["estado"] == "error_peticion"


def test_ajuste_regional_reproduce_resultado_de_la_comunidad(servicio):
    d, _, _ = servicio._encuesta("02-202307", "01")
    w, info = servicio._pesos(d, "02-202307", "resultado_oficial", "01")
    assert info["referencia"] == "Andalucía"
    partido = np.array([v is not None and v not in servicio._NO_PARTIDO for v in d["voto"]])
    i = servicio.P.nivel("ccaa")["ids"].index("ES-CA-01")
    for fam in ("PP", "PSOE"):
        decl = w[partido & (d["voto"] == fam)].sum() / w[partido].sum()
        assert decl == pytest.approx(servicio.P.serie("ccaa", "voto_familia", "02-202307", fam)[i], abs=1e-6)


def test_comparar_comunidades(servicio):
    d = servicio.ejecutar("votantes_regiones", {"familia": "PP", "dimension": "grupo_edad", "categoria": "65 y más"})["resultado"]
    assert len(d["filas"]) >= 17 and all(f["ic"][0] <= f["p"] <= f["ic"][1] for f in d["filas"])
    assert {f["fiabilidad"] for f in d["filas"]} <= {"alta", "media", "baja"}
    assert servicio.ejecutar("votantes_regiones", {"dimension": "ccaa"})["ejecucion"]["estado"] == "error_peticion"
