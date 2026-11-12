"""Candidaturas proclamadas al Congreso (29-N-2026) desde el BOE oficial.

Fuente: BOE núm. 273, de 3 de noviembre de 2026, disposición BOE-A-2026-23103
(«Candidaturas proclamadas para las elecciones al Congreso de los Diputados y al Senado,
convocadas por Real Decreto 806/2026, de 5 de octubre»). El PDF se descarga de boe.es,
se guarda con su SHA-256 en data/landing/boe_2026/ y se convierte a texto con pypdf.

Solo se guardan la circunscripción, el orden en la papeleta, la denominación, las siglas, el
número de candidatos titulares y la cabeza de lista (dato público del BOE). No se guarda el resto
de nombres.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pandas as pd

from ..paths import LANDING

BOE_ID = "BOE-A-2026-23103"
BOE_URL = "https://www.boe.es/boe/dias/2026/11/03/pdfs/BOE-A-2026-23103.pdf"
DIR = LANDING / "boe_2026"
PDF = DIR / f"{BOE_ID}.pdf"
SHA256 = "4f437d2d6aedc7c3283649912e38c883c3d34cfd00b1647c36915f0cb95874dc"

# Nombre de la Junta Electoral en el BOE -> código INE de provincia
JUNTAS = {
    "ALBACETE": "02", "ALICANTE": "03", "ALMERIA": "04", "ALAVA": "01", "ASTURIAS": "33",
    "AVILA": "05", "BADAJOZ": "06", "ILLES BALEARS": "07", "BARCELONA": "08", "BIZKAIA": "48",
    "BURGOS": "09", "CACERES": "10", "CADIZ": "11", "CANTABRIA": "39", "CASTELLON": "12",
    "CIUDAD REAL": "13", "CORDOBA": "14", "A CORUNA": "15", "CUENCA": "16", "GIPUZKOA": "20",
    "GIRONA": "17", "GRANADA": "18", "GUADALAJARA": "19", "HUELVA": "21", "HUESCA": "22",
    "JAEN": "23", "LEON": "24", "LLEIDA": "25", "LUGO": "27", "MADRID": "28", "MALAGA": "29",
    "MURCIA": "30", "NAVARRA": "31", "OURENSE": "32", "PALENCIA": "34", "LAS PALMAS": "35",
    "PONTEVEDRA": "36", "LA RIOJA": "26", "SALAMANCA": "37", "SANTA CRUZ DE TENERIFE": "38",
    "SEGOVIA": "40", "SEVILLA": "41", "SORIA": "42", "TARRAGONA": "43", "TERUEL": "44",
    "TOLEDO": "45", "VALENCIA": "46", "VALLADOLID": "47", "ZAMORA": "49", "ZARAGOZA": "50",
    "CEUTA": "51", "MELILLA": "52",
}

_RUIDO = re.compile(r"^(BOLETÍN OFICIAL DEL ESTADO|Núm\. \d+ |cve: BOE|Verificable en)")
_JUNTA = re.compile(r"^JUNTA ELECTORAL (?:PROVINCIAL )?DE (.+?)\s*$")
_ITEM = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def verificar_pdf(path: Path = PDF) -> None:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    if h != SHA256:
        raise ValueError(f"{path.name}: SHA-256 {h} no coincide con el registrado ({SHA256})")


def texto_boe(path: Path = PDF) -> str:
    cache = path.with_suffix(".txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    import pypdf
    verificar_pdf(path)
    txt = "\n".join(p.extract_text() for p in pypdf.PdfReader(str(path)).pages)
    cache.write_text(txt, encoding="utf-8")
    return txt


def _es_partido_legacy(texto: str) -> bool:
    """Las cabeceras de candidatura terminan en ')' (siglas); los candidatos terminan en '.'."""
    return texto.endswith(")")


def parsear(txt: str) -> pd.DataFrame:
    lineas = [l.rstrip() for l in txt.splitlines() if l.strip() and not _RUIDO.match(l)]
    filas, prov, seccion, actual, en_suplentes = [], None, None, None, False
    i = 0
    while i < len(lineas):
        l = lineas[i].strip()
        m = _JUNTA.match(l)
        if m:
            nombre = _norm(m.group(1))
            if nombre not in JUNTAS:
                raise ValueError(f"Junta no reconocida: {m.group(1)!r}")
            prov, seccion = JUNTAS[nombre], None
            i += 1
            continue
        if l.startswith("CONGRESO DE LOS DIPUTADOS"):
            seccion = "congreso"
            i += 1
            continue
        if l == "SENADO":
            seccion = "senado"
            i += 1
            continue
        if seccion != "congreso":
            i += 1
            continue
        if l.startswith("Suplente"):
            en_suplentes = True
            i += 1
            continue
        if l.startswith("No proclamada") and actual is not None:
            actual["proclamada"] = False
            i += 1
            continue
        m = _ITEM.match(l)
        if m:
            texto, num = m.group(2), int(m.group(1))
            siguiente_partido = (filas[-1]["orden_papeleta"] + 1
                                 if filas and filas[-1]["provincia_id"] == prov else 1)
            # una cabecera de candidatura puede partirse en varias líneas hasta cerrar las siglas
            j = i
            while (not texto.endswith(".") and not texto.endswith(")")
                   and j + 1 < len(lineas) and not _ITEM.match(lineas[j + 1].strip())
                   and not lineas[j + 1].strip().startswith(("No proclamada", "Titular", "Suplente",
                                                             "SENADO", "JUNTA"))):
                j += 1
                texto = f"{texto} {lineas[j].strip()}"
            # Cabecera = número consecutivo de papeleta y texto que no acaba en punto
            # (los candidatos siempre acaban en punto en el BOE).
            if num == siguiente_partido and not texto.endswith("."):
                k = len(texto)
                if texto.endswith(")"):
                    prof = 0   # '(' que equilibra el último ')' (siglas con paréntesis anidados)
                    for pos in range(len(texto) - 1, -1, -1):
                        prof += texto[pos] == ")"
                        prof -= texto[pos] == "("
                        if prof == 0:
                            k = pos
                            break
                actual = {
                    "provincia_id": prov, "orden_papeleta": num,
                    "denominacion": texto[:k].strip(),
                    "siglas": texto[k + 1:-1].strip() if k < len(texto) else texto.strip(),
                    "n_titulares": 0, "cabeza_lista": None, "proclamada": True,
                }
                filas.append(actual)
                en_suplentes = False
            elif actual is not None and not en_suplentes:
                actual["n_titulares"] += 1
                if actual["cabeza_lista"] is None:
                    actual["cabeza_lista"] = texto.rstrip(".")
            i = j + 1
            continue
        i += 1
    df = pd.DataFrame(filas)
    df["fuente"] = f"{BOE_ID} ({BOE_URL})"
    return df


def cargar() -> pd.DataFrame:
    return parsear(texto_boe())
