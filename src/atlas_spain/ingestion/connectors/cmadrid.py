"""Conector Datos Abiertos Comunidad de Madrid: elecciones a la Asamblea de Madrid (1991–2023).

Ficheros (CKAN, CSV ';' UTF-8):
  - "Elecciones. Asamblea. Municipios": electores, votantes, nulos, blancos… por municipio
  - "Elecciones. Asamblea. Votos por candidaturas. Municipios": votos por candidatura
  - "Asamblea. Diputados": escaños por partido (texto "Diputados de X en la Asamblea…")

Limitaciones de la fuente (se documentan, no se corrigen):
  - Solo se desglosan las candidaturas principales; el resto llega agregado como
    "Resto de partidos".
  - 2003 aparece una sola vez aunque hubo dos convocatorias (mayo y octubre).

Salida: mismo formato largo que el conector de Euskadi (gold.fact_regional_results).
"""

from __future__ import annotations

import io
import re

import pandas as pd

from atlas_spain.http import fetch
from atlas_spain.ingestion.runner import Execution

URLS = {
    "participacion": "https://datos.comunidad.madrid/dataset/1e80b4d4-f949-4a60-bda1-9ac2ebc3a637/resource/b1136f11-47d4-4acc-8dc6-3e3ff3a9bb69/download/elecciones.-asamblea.-municipios.csv",
    "votos": "https://datos.comunidad.madrid/dataset/6e1cd790-c1c0-42f0-99e1-b1f9879bde27/resource/d15a8810-704d-443d-ac24-3f6b14727324/download/elecciones.-asamblea.-votos-por-candidaturas.-municipios.csv",
    "diputados": "https://datos.comunidad.madrid/dataset/c094c56d-5197-4458-b502-1900b25b09a7/resource/332f417f-3bf8-4fd3-85da-a3c7cc69fc64/download/asamblea.-diputados.csv",
}
MEDIDAS = {"Electores": "censo", "Votantes": "votantes", "Votos nulos": "nulos", "Votos en blanco": "blancos",
           "Votos válidos": "validos", "Votos a candidaturas": "votos_candidaturas"}
# Texto del concepto de diputados -> nombre de candidatura en el fichero de votos
DIPUTADOS = {"Partido Popular (PP)": "PP", "Partido Socialista Obrero Español (PSOE)": "PSOE", "Más Madrid": "Más Madrid",
             "Vox": "Vox", "Podemos": "Podemos", "Ciudadanos (CS)": "CS", "Izquierda Unida (IU)": "IU",
             "Unión Progreso y Democrácia (UPyD)": "UPyD", "Unión Progreso y Democracia (UPyD)": "UPyD",
             "resto de partidos": "Resto de partidos"}


def _csv(raw: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw), sep=";", dtype=str, encoding="utf-8-sig")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce")


def _geo(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["Tipo territorio"].isin(["Comunidad de Madrid", "Municipios"])].copy()
    df["nivel"] = df["Tipo territorio"].map({"Comunidad de Madrid": "territorio", "Municipios": "municipio"})
    # Código de 4 cifras = municipio (3) + dígito de control
    df["municipio_ine"] = ("28" + df["Código territorio"].fillna("").str.zfill(4).str[:3]).where(df["nivel"] == "municipio")
    df["provincia_ine"] = "28"
    return df


def build(part: pd.DataFrame, votos: pd.DataFrame, dip: pd.DataFrame) -> pd.DataFrame:
    part, votos = _geo(part), _geo(votos)
    part["campo"] = part["Medida"].map(MEDIDAS)
    p = (part.dropna(subset=["campo"]).assign(valor=lambda d: _num(d["Valor"]))
         .pivot_table(index=["Año", "nivel", "municipio_ine", "provincia_ine"], columns="campo", values="valor",
                      aggfunc="first", dropna=False).reset_index())
    v = votos.assign(votos=_num(votos["Valor"])).rename(columns={"Candidatura": "candidatura"})
    v = v[["Año", "nivel", "municipio_ine", "provincia_ine", "candidatura", "votos"]]
    # escaños: solo filas totales "Diputados de/del X en la Asamblea…" (no las de hombres/mujeres)
    d = dip[dip["Concepto"].str.match(r"^Diputados (de|del) ") & (dip["Valor"] != "-")].copy()
    d["partido"] = d["Concepto"].str.extract(r"^Diputados (?:de|del) (.+?) en la Asamblea")[0]
    d["candidatura"] = d["partido"].map(DIPUTADOS)
    d = d.dropna(subset=["candidatura"]).assign(escanos=lambda x: _num(x["Valor"]), nivel="territorio")
    v = v.merge(d[["Año", "nivel", "candidatura", "escanos"]], on=["Año", "nivel", "candidatura"], how="left")
    out = v.merge(p, on=["Año", "nivel", "municipio_ine", "provincia_ine"], how="left")
    out["anyo"] = out["Año"].astype(int)
    out["convocatoria"] = "A" + out["Año"]
    out["election_key"] = "MAD-A" + out["Año"]
    out["tipo"] = "asamblea_madrid"
    return out.drop(columns=["Año"])


def extract(ex: Execution, **_) -> str | None:
    raws = {}
    for k, url in URLS.items():
        r = fetch(url, timeout=180)
        ex.save_raw(f"{k}.csv", r.content)
        raws[k] = _csv(r.content)
    df = build(raws["participacion"], raws["votos"], raws["diputados"])
    ex.records_downloaded = len(df)
    for k in df.columns:
        if df[k].dtype == object:
            df[k] = df[k].astype("string")
    ex.save_parquet("asamblea", df)
    return None
