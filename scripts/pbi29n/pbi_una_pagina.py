"""Crea una copia del informe PBIP con UNA sola página (mismo modelo semántico) para abrirla en equipos con poca RAM.

Uso: python pbi_una_pagina.py <nombre_pagina>   ->  reports/powerbi/captura/ATLAS_captura.pbip
"""
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2] / "reports" / "powerbi_29n"
NOMBRE = "ATLAS_Espana_29N"


def crear(pagina: str, cambios: dict[str, str] | None = None) -> Path:
    """cambios: {'valor actual del segmentador': 'valor nuevo'} (p. ej. {'GUAYAS': 'PICHINCHA'})."""
    dst = RAIZ / "captura"
    rep = dst / "ATLAS_captura.Report"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(RAIZ / f"{NOMBRE}.Report", rep, ignore=shutil.ignore_patterns(".pbi"))
    pags = rep / "definition" / "pages"
    for d in pags.iterdir():
        if d.is_dir() and d.name != pagina:
            shutil.rmtree(d)
    for v in (pags / pagina).rglob("visual.json"):
        t = v.read_text(encoding="utf-8")
        for a, b in (cambios or {}).items():
            t = t.replace(f"'{a}'", f"'{b}'")
        v.write_text(t, encoding="utf-8")
    meta = json.loads((pags / "pages.json").read_text(encoding="utf-8"))
    meta.update(pageOrder=[pagina], activePageName=pagina)
    (pags / "pages.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    pbir = json.loads((rep / "definition.pbir").read_text(encoding="utf-8"))
    pbir["datasetReference"] = {"byPath": {"path": f"../../{NOMBRE}.SemanticModel"}}
    (rep / "definition.pbir").write_text(json.dumps(pbir, indent=2), encoding="utf-8")
    plat = json.loads((rep / ".platform").read_text(encoding="utf-8"))
    plat["metadata"]["displayName"] = "ATLAS_captura"
    (rep / ".platform").write_text(json.dumps(plat, indent=2), encoding="utf-8")
    pbip = dst / "ATLAS_captura.pbip"
    pbip.write_text(json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
                                "version": "1.0", "artifacts": [{"report": {"path": "ATLAS_captura.Report"}}],
                                "settings": {"enableAutoRecovery": False}}, indent=2), encoding="utf-8")
    return pbip


if __name__ == "__main__":
    print(crear(sys.argv[1], dict(a.split("=", 1) for a in sys.argv[2:])))
