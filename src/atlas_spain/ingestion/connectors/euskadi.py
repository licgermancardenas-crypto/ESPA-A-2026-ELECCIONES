"""Conector Open Data Euskadi: resultados electorales en la CAPV.

Ficheros por convocatoria: {Tipo}{AA}_c.zip con Cir (territorio histórico),
Mun (municipio) y Mes (mesa). Dos formatos:
  - antiguo: una cabecera, separador ',', columnas de partido = votos;
  - nuevo: dos filas de cabecera (partido / métrica), separador ';'.

Escaños: solo cuando el fichero los publica (formato nuevo, nivel territorio).
No se recalculan: ver config/electoral_systems.yaml (País Vasco sin verificar).
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile

import pandas as pd

from atlas_spain.http import fetch
from atlas_spain.ingestion.runner import Execution

URL = "https://opendata.euskadi.eus/contenidos/informacion/w_em_descargas/es_def/adjuntos/csv/{c}_c.zip"
# P = Parlamento Vasco, G = Congreso (resultados en la CAPV)
CONVOCATORIAS = ["P80", "P84", "P86", "P90", "P94", "P98", "P01", "P05", "P09", "P12", "P16", "P20", "P24", "G23"]
TH = {"ARABA": "01", "ALAVA": "01", "BIZKAIA": "48", "GIPUZKOA": "20"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", s).strip()


def _num(x):
    if x is None:
        return None
    x = str(x).strip().replace("\t", "").strip('"')
    if x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def _code(x) -> str:
    return re.sub(r"\D", "", str(x or ""))


def _provincia(th: str) -> str | None:
    t = _norm(th)
    for k, v in TH.items():
        if k in t:
            return v
    return None


COMUNES = {  # nombre normalizado -> campo ATLAS
    "TH": "th", "AMBITO": "ambito", "MUNICIPIO": "municipio", "COD MUNICIPIO": "cod_municipio",
    "COD.MUNICIPIO": "cod_municipio", "COD.COMARCA": "cod_comarca", "DISTRITO": "distrito",
    "SECCION": "seccion", "MESA": "mesa", "CENSO": "censo", "VOTANTES": "votantes", "VOTOS": "votantes",
    "NULOS": "nulos", "VALIDOS": "validos", "BLANCOS": "blancos", "VOTOS CAND.": "votos_candidaturas",
    "VOTOS CANDIDATURAS": "votos_candidaturas", "ABSTENCION": "abstencion", "ABSTENCIONES": "abstencion",
    "NOTA ELECCION": "nota_eleccion", "NOTA": "nota",
}


def parse_csv(raw: bytes) -> pd.DataFrame:
    text = raw.decode("latin-1")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    sep = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    rows = [ln.split(sep) for ln in lines]
    r0 = [c.strip() for c in rows[0]]
    dos_cabeceras = (not r0[0]) or _norm(r0[0]).startswith("LISTADO")
    if dos_cabeceras:
        partidos, metricas, datos = r0, [c.strip() for c in rows[1]], rows[2:]
    else:
        metricas, datos = r0, rows[1:]
        partidos = [""] * len(metricas)
        # en el formato antiguo todo lo posterior a la abstención son partidos (votos)
        corte = max(i for i, m in enumerate(metricas) if _norm(m) in ("ABSTENCION", "ABSTENCIONES")) + 1
        partidos = [""] * corte + metricas[corte:]
        metricas = metricas[:corte] + ["V. CANDIDATURA"] * (len(metricas) - corte)
    largos = []
    for fila in datos:
        fila = fila + [""] * (len(metricas) - len(fila))
        comun, por_partido = {}, {}
        for j, m in enumerate(metricas):
            p = partidos[j] if j < len(partidos) else ""
            mn = _norm(m).rstrip()
            if not p or _norm(p).startswith("LISTADO"):
                campo = COMUNES.get(mn)
                if campo:
                    comun[campo] = fila[j].strip().strip('"').replace("\t", "").strip()
                continue
            d = por_partido.setdefault(p.strip(), {})
            if mn.startswith("V. CANDIDATURA"):
                d["votos"] = _num(fila[j])
            elif mn.startswith("ESCA"):
                d["escanos"] = _num(fila[j])
        nombre_territorio = comun.get("th") or comun.get("ambito") or ""
        if _norm(nombre_territorio) in ("", "TH", "TOTAL") or "EUSKADI" in _norm(nombre_territorio):
            continue
        for partido, d in por_partido.items():
            if not partido:
                continue
            largos.append({**comun, "candidatura": partido, "votos": d.get("votos"), "escanos": d.get("escanos")})
    df = pd.DataFrame(largos)
    if df.empty:
        return df
    for c in ("censo", "votantes", "nulos", "validos", "blancos", "votos_candidaturas", "abstencion"):
        if c in df:
            df[c] = df[c].map(_num)
    df["provincia_ine"] = (df["th"] if "th" in df else df["ambito"]).map(_provincia)
    if "cod_municipio" in df:
        df["municipio_ine"] = df["provincia_ine"] + df["cod_municipio"].map(_code).str.zfill(3)
    for c in ("distrito", "seccion"):
        if c in df:
            df[c] = df[c].map(_code)
    if "mesa" in df:
        df["mesa"] = df["mesa"].str.replace(r"[\s\"]", "", regex=True)
    return df


def extract(ex: Execution, convocatorias: list[str] | None = None, **_) -> str | None:
    for c in convocatorias or CONVOCATORIAS:
        try:
            r = fetch(URL.format(c=c), timeout=180)
            ex.save_raw(f"{c}_c.zip", r.content)
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                for info in zf.infolist():
                    base = info.filename.rsplit("/", 1)[-1]
                    m = re.match(r"(Cir|Mun|Mes)", base)
                    if not m or not base.lower().endswith(".csv"):
                        continue
                    nivel = {"Cir": "territorio", "Mun": "municipio", "Mes": "mesa"}[m.group(1)]
                    df = parse_csv(zf.read(info))
                    if df.empty:
                        continue
                    df["convocatoria"] = c
                    df["tipo"] = {"P": "parlamento_vasco", "G": "congreso"}[c[0]]
                    yy = int(c[1:])
                    df["anyo"] = 1900 + yy if yy > 50 else 2000 + yy
                    df["nivel"] = nivel
                    df["fichero"] = info.filename
                    ex.records_downloaded += len(df)
                    ex.save_parquet(f"{c}_{nivel}", df.astype({k: "string" for k in df.columns
                                                               if df[k].dtype == object}))
        except Exception as exc:
            ex.errors += 1
            ex.error_detail = ((ex.error_detail or "") + f"{c}: {type(exc).__name__}: {exc}\n")[:4000]
    return "partial" if ex.errors else None
