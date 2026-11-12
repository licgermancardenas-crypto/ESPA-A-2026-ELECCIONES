"""Tests del motor de pronóstico 29-N-2026, incluidas las pruebas de ausencia de fuga de información."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from atlas_spain.paths import WAREHOUSE
from atlas_spain.pronostico import candidaturas, datos, encuestas_wiki, features, modelos, simulacion

hay_warehouse = pytest.mark.skipif(not WAREHOUSE.exists(), reason="sin warehouse local")
hay_boe = pytest.mark.skipif(not candidaturas.PDF.exists(), reason="sin el PDF del BOE en data/landing")
hay_wiki = pytest.mark.skipif(not encuestas_wiki.WIKITEXT.exists(), reason="sin encuestas en data/landing")


# ------------------------------------------------------------------------------ unitarios

def test_dhondt_ejemplo_clasico():
    # Ejemplo de manual: 7 escaños, votos 340k/280k/160k/60k/15k
    v = np.array([[340, 280, 160, 60, 15]], float)
    v = v / v.sum()
    e = simulacion.dhondt(v, 7, np.ones(5, bool), barrera=0.0)[0]
    assert e.tolist() == [3, 3, 1, 0, 0]


def test_dhondt_barrera_y_otros():
    v = np.array([[0.50, 0.29, 0.025, 0.185]])
    e = simulacion.dhondt(v, 10, np.array([True, True, True, False]), barrera=0.03)[0]
    assert e[2] == 0 and e[3] == 0 and e.sum() == 10


def test_softmax_suma_uno_por_grupo():
    eta = np.array([0.1, 2.0, -1.0, 0.5, 0.5])
    g = np.array([0, 0, 0, 1, 1])
    p = modelos.softmax_grupos(eta, g)
    assert np.allclose(pd.Series(p).groupby(g).sum(), 1.0)


def test_parser_boe_sintetico():
    txt = """JUNTA ELECTORAL DE SORIA
CONGRESO DE LOS DIPUTADOS
1. PARTIDO POPULAR (PP)
1. Ana Uno.
2. Luis Dos.
Suplentes:
1. Eva Tres.
2. SORIA ¡YA! (SY)
1. Pedro Cuatro (Independiente).
2. Marta Cinco.
3. FEMINISM8 (F8)
No proclamada.
4. FRENTE OBRERO
1. Juan Seis.
2. Rosa Siete.
SENADO
1. PARTIDO POPULAR (PP)
1. Otra Persona.
"""
    d = candidaturas.parsear(txt)
    assert d.siglas.tolist() == ["PP", "SY", "F8", "FRENTE OBRERO"]
    assert d.proclamada.tolist() == [True, True, False, True]
    assert d.n_titulares.tolist() == [2, 2, 0, 2]
    assert d.cabeza_lista.iloc[1] == "Pedro Cuatro (Independiente)"
    assert set(d.provincia_id) == {"42"}


def test_fechas_wikipedia():
    assert encuestas_wiki._fechas("26 Oct–10 Nov", 2026) == (date(2026, 10, 26), date(2026, 11, 10))
    assert encuestas_wiki._fechas("28 Dec–3 Jan", 2026) == (date(2025, 12, 28), date(2026, 1, 3))
    assert encuestas_wiki._fechas("5 Nov", 2026) == (date(2026, 11, 5), date(2026, 11, 5))


def test_media_encuestas_corta_en_fecha():
    polls = pd.DataFrame({
        "instituto": ["A", "B", "C"], "campo_fin": [date(2026, 11, 1), date(2026, 11, 5), date(2026, 11, 20)],
        "muestra": [1000, 1000, 1000], "PP": [30.0, 32.0, 99.0]})
    media, usadas = datos.media_encuestas(polls, {"PP": ["PP"]}, date(2026, 11, 10))
    assert "C" not in set(usadas.instituto)          # posterior al corte: no entra
    assert 0.30 < media["PP"] < 0.32


# ------------------------------------------------------------------------- datos reales

@hay_boe
def test_candidaturas_boe_cuadran_con_el_boe():
    d = candidaturas.cargar()
    assert d.proclamada.sum() == 534 and (~d.proclamada).sum() == 21   # cifras oficiales publicadas
    p = d[d.proclamada]
    assert p.provincia_id.nunique() == 52
    assert p.groupby("provincia_id").n_titulares.max().sum() == 350
    assert p.groupby("provincia_id").n_titulares.max()["28"] == 38


@hay_warehouse
@hay_wiki
def test_sin_fuga_encuestas_en_backtest():
    """Ninguna encuesta usada para un objetivo termina su campo después de la elección − 6 días."""
    cfg = datos.config()
    for bt in cfg["backtest"]:
        features.diseno_historico(bt)
        usadas = features.META[bt["objetivo"]]["encuestas_usadas"]
        corte = date.fromisoformat(bt["fecha"]) - timedelta(days=cfg["encuestas"]["corte_previo_eleccion_dias"])
        assert len(usadas) > 0
        assert max(usadas.campo_fin) <= corte, bt["objetivo"]


@hay_warehouse
def test_sin_fuga_elecciones_previas():
    """La elección previa y las europeas usadas son siempre anteriores al objetivo."""
    for bt in datos.config()["backtest"]:
        for clave in ("previa", "europeas"):
            if bt.get(clave):
                assert bt[clave][3:] < bt["objetivo"][3:], (bt["objetivo"], clave)


@hay_warehouse
@hay_wiki
def test_sin_fuga_resultado_objetivo_no_altera_prediccion():
    """Prueba de fuga: si se sustituye el resultado observado del objetivo por ruido, la predicción
    (entrenada solo con transiciones anteriores) no cambia en absoluto."""
    from atlas_spain.pronostico import backtest
    D = backtest.disenos()
    train, objetivo = backtest._cat(D[:3]), D[3].copy()
    m = modelos.LogitCondicional(1.0).fit(train)
    p1 = modelos.predecir(m, objetivo)
    ruido = objetivo.copy()
    ruido["s"] = np.random.default_rng(0).dirichlet(np.ones(len(ruido)))
    p2 = modelos.predecir(m, ruido)
    assert np.array_equal(p1, p2)
    # y entrenar con un objetivo alterado SÍ cambiaría el modelo (el test es sensible)
    m2 = modelos.LogitCondicional(1.0).fit(backtest._cat(D[:2] + [ruido.assign(eleccion="x")]))
    assert not np.allclose(m.theta_, m2.theta_)


@hay_warehouse
@hay_wiki
@hay_boe
def test_diseno_2026_coherente():
    df, media = features.diseno_2026(date(2026, 11, 12))
    assert df.provincia_id.nunique() == 52
    assert df.s.isna().all()                        # 2026: sin resultado
    assert (df.groupby("provincia_id").bloque.apply(lambda s: (s == "OTROS").sum()) == 1).all()
    assert 0.25 < media["PP"] < 0.40 and 0.20 < media["PSOE"] < 0.35
    # solo bloques con candidatura proclamada en la provincia
    assert not ((df.provincia_id == "08") & (df.bloque == "PODEMOS")).any()
