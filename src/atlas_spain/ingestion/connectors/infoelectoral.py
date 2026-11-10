"""Conector Infoelectoral (Ministerio del Interior).

Orden de búsqueda por cada convocatoria:
  1. data/landing/infoelectoral/{TT}{AAAAMM}_{NIVEL}.zip  (carga manual)
  2. Descarga directa desde infoelectoral.interior.gob.es

El servidor está detrás de un desafío anti-bot (Cloudflare). Si responde con el
desafío, la convocatoria queda registrada como 'blocked' y NO se intenta
eludir: hay que bajar el ZIP desde un navegador y dejarlo en landing/.
"""

from __future__ import annotations

import yaml

from atlas_spain import paths
from atlas_spain.http import BlockedByChallenge, fetch
from atlas_spain.ingestion.runner import Execution
from atlas_spain.parsers.infoelectoral_dat import parse_zip

BASE = "https://infoelectoral.interior.gob.es/estaticos/docxl/apliextr/{name}"
LANDING = paths.LANDING / "infoelectoral"


def catalog() -> dict:
    with open(paths.CONFIG / "elections.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["infoelectoral"]


def zip_name(tipo: str, aaaamm: str, nivel: str) -> str:
    return f"{tipo}{aaaamm}_{nivel}.zip"


def _obtain(name: str) -> tuple[bytes, str]:
    local = LANDING / name
    if local.exists():
        return local.read_bytes(), "landing"
    r = fetch(BASE.format(name=name), timeout=180, retries=1)
    if not r.content.startswith(b"PK"):
        raise ValueError(f"{name}: la respuesta no es un ZIP ({r.content_type})")
    return r.content, "download"


def extract(ex: Execution, tipo: str, convocatorias: list[str] | None = None,
            niveles: tuple[str, ...] = ("MUNI",)) -> str | None:
    cat = catalog()[tipo]
    convs = convocatorias or cat["convocatorias"]
    LANDING.mkdir(parents=True, exist_ok=True)
    blocked, ok = [], 0
    for conv in convs:
        for nivel in niveles:
            name = zip_name(tipo, conv, nivel)
            try:
                content, origin = _obtain(name)
            except BlockedByChallenge:
                blocked.append(name)
                continue
            except Exception as exc:
                ex.errors += 1
                ex.error_detail = ((ex.error_detail or "") + f"{name}: {exc}\n")[:4000]
                continue
            ex.save_raw(name, content)
            frames = parse_zip(content)
            if not frames:
                ex.errors += 1
                ex.error_detail = ((ex.error_detail or "") + f"{name}: ZIP sin ficheros DAT reconocidos\n")[:4000]
                continue
            for ftype, df in frames.items():
                # Algunos ZIP (municipales) incluyen ficheros de otro tipo de elección (p. ej. 10):
                # se conservan solo los registros de la elección pedida.
                df = df[df["tipo_eleccion"] == tipo].copy()
                if df.empty:
                    continue
                df["_zip"] = name
                df["_origen"] = origin
                df["nivel_zip"] = nivel
                ex.records_downloaded += len(df)
                ex.save_parquet(f"f{ftype}_{nivel.lower()}_{conv}", df)
            ok += 1
    if blocked:
        note = (f"{len(blocked)} ZIP bloqueados por desafío anti-bot. Descargar manualmente a "
                f"{LANDING} : " + ", ".join(blocked[:20]))
        ex.error_detail = ((ex.error_detail or "") + note)[:4000]
    if ok == 0:
        return "blocked" if blocked and not ex.errors else "failed"
    return "partial" if (blocked or ex.errors) else None
