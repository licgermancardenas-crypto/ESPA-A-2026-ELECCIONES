"""Conector Datos Abiertos del Congreso de los Diputados (diputados).

Los ficheros llevan sello temporal en el nombre (DiputadosActivos__AAAAMMDDhhmmss.json),
así que se resuelve el enlace vigente leyendo la página del catálogo.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from atlas_spain.http import fetch
from atlas_spain.ingestion.runner import Execution

PAGE = "https://www.congreso.es/es/opendata/diputados"
HOST = "https://www.congreso.es"
PATTERNS = {
    "activos": r'href="(/webpublica/opendata/diputados/DiputadosActivos__\d+\.json)"',
    "baja": r'href="(/webpublica/opendata/diputados/DiputadosDeBaja__\d+\.json)"',
}

# Campos que no se publican en ATLAS aunque vengan en origen (minimización).
DROP = {"FECHANACIMIENTO", "LUGARNACIMIENTO"}


def extract(ex: Execution) -> str | None:
    html = fetch(PAGE, timeout=60).content.decode("utf-8", "replace")
    for kind, pat in PATTERNS.items():
        m = re.search(pat, html)
        if not m:
            ex.errors += 1
            ex.error_detail = ((ex.error_detail or "") + f"enlace '{kind}' no encontrado\n")
            continue
        url = HOST + m.group(1)
        r = fetch(url, timeout=60)
        ex.save_raw(url.rsplit("/", 1)[-1], r.content)
        data = json.loads(r.content.decode("utf-8-sig"))
        df = pd.DataFrame(data)
        df = df[[c for c in df.columns if c.upper() not in DROP]]
        df["estado"] = kind
        df["fichero_origen"] = url
        ex.records_downloaded += len(df)
        ex.save_parquet(f"diputados_{kind}", df)
    return "partial" if ex.errors else None
