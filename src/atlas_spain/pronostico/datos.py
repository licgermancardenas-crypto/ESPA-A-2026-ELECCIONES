"""Datos de entrada del motor: resultados oficiales por provincia, medias de encuestas y diseño.

Unidad de análisis: (contienda = circunscripción provincial, bloque). La proporción de cada bloque es
sobre los votos a candidaturas de la circunscripción (suma 1). OTROS agrupa el resto de candidaturas.
"""
from __future__ import annotations

import functools
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd
import yaml

from ..paths import CONFIG, WAREHOUSE
from . import encuestas_wiki

OTROS = "OTROS"


@functools.lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((CONFIG / "pronostico_2026.yaml").read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=16)
def resultados(eleccion: str) -> pd.DataFrame:
    """provincia_id (2 díg.), familia, votos, escanos; votos a candidaturas por provincia."""
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        df = con.sql(
            "select right(geo_id, 2) provincia_id, familia, sum(votos)::double votos, "
            "sum(escanos)::double escanos from gold.results_by_family "
            "where election_id = ? and geo_level = 'provincia' group by 1, 2",
            params=[eleccion]).df()
    finally:
        con.close()
    if df.empty:
        raise ValueError(f"Sin resultados para {eleccion}")
    return df


def escanos_por_provincia(eleccion: str) -> pd.Series:
    return resultados(eleccion).groupby("provincia_id").escanos.sum()


def shares(eleccion: str, grupos: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Tabla ancha provincia x clave con proporciones. `grupos` agrega familias en una clave;
    las familias no mencionadas van a OTROS. Sin grupos, cada familia es su propia clave."""
    r = resultados(eleccion).copy()
    if grupos is not None:
        inv = {f: k for k, fs in grupos.items() for f in fs}
        r["clave"] = r.familia.map(inv).fillna(OTROS)
    else:
        r["clave"] = r.familia
    t = r.pivot_table(index="provincia_id", columns="clave", values="votos", aggfunc="sum", fill_value=0.0)
    return t.div(t.sum(1), axis=0)


def votos_validos(eleccion: str) -> pd.Series:
    return resultados(eleccion).groupby("provincia_id").votos.sum()


# ---------------------------------------------------------------------------------- encuestas

@functools.lru_cache(maxsize=16)
def encuestas(pagina: str) -> pd.DataFrame:
    if pagina == "2026":
        return encuestas_wiki.parsear()
    anio = {"2015": 2015, "2016": 2016, "April_2019": 2019, "November_2019": 2019, "2023": 2023}[pagina]
    txt = (encuestas_wiki.DIR / f"wiki_polls_{pagina}.wikitext").read_text(encoding="utf-8")
    url = f"https://en.wikipedia.org/wiki/Opinion_polling_for_the_{pagina}_Spanish_general_election"
    return encuestas_wiki.parsear(txt, anio, url)


def seleccionar_encuestas(polls: pd.DataFrame, corte: date) -> pd.DataFrame:
    """Encuestas usables a una fecha de corte (sin fuga: fin de campo <= corte)."""
    p = config()["encuestas"]
    d = polls[(polls.campo_fin <= corte) & (polls.campo_fin > corte - timedelta(days=p["ventana_dias"]))]
    d = d[~d.instituto.str.contains("election", case=False)]
    if p["una_por_instituto"]:
        d = d.sort_values("campo_fin").groupby("instituto", as_index=False).tail(1)
    return d.copy()


def media_encuestas(polls: pd.DataFrame, columnas: dict[str, list[str]], corte: date) -> tuple[dict, pd.DataFrame]:
    """Media ponderada (recencia y √muestra) de cada columna de encuesta, en proporción (0-1).
    `columnas`: columna de Wikipedia -> claves destino (si son varias, la columna es una suma conjunta
    y se reparte según el resultado previo: lo resuelve el llamador). Devuelve {columna: media}."""
    p = config()["encuestas"]
    d = seleccionar_encuestas(polls, corte)
    if d.empty:
        return {}, d
    edad = np.array([(corte - f).days for f in d.campo_fin])
    w = 0.5 ** (edad / p["vida_media_dias"]) * np.sqrt(d.muestra.fillna(1000).clip(400, 10000).to_numpy() / 1000)
    d["peso"] = w / w.sum()
    out = {}
    for col in columnas:
        if col not in d:
            continue
        v = d[col].to_numpy(float)
        ok = ~np.isnan(v)
        if ok.sum() == 0:
            continue
        out[col] = float(np.sum(v[ok] * w[ok]) / np.sum(w[ok])) / 100.0
    return out, d
