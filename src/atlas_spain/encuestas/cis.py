"""Microdatos de las encuestas postelectorales del CIS (elecciones generales 2015–2023).

    python -m atlas_spain.encuestas.cis   → data/gold/cis_postelectorales.parquet + cis_estudios.json

Origen: ficheros MDxxxx.zip descargados de www.cis.es (formulario de solicitud del CIS) y guardados
sin modificar en data/landing/cis/ (se registra su SHA-256). Licencia: condiciones de reutilización
del CIS (citar la fuente).

Armonización entre estudios (las preguntas y códigos cambian de una encuesta a otra):
- voto: recuerdo de voto en la elección del estudio (variable recodificada del CIS), traducido a las
  familias políticas de Atlas; «Abstención» y «Blanco o nulo» se conservan; No recuerda / N.C. /
  sin derecho a voto quedan como faltantes.
- voto_anterior: recuerdo de voto en la elección general previa (permite trasvases declarados).
- sexo, edad (y tramos), estudios (recodificación del CIS), situación laboral, ideología (1–10),
  tamaño de municipio, comunidad autónoma y peso (PESO cuando el diseño lo exige; 1 cuando la
  ficha técnica indica «Ponderación: no procede»).

No contiene datos identificativos: los ficheros del CIS están anonimizados.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from atlas_spain import paths

LANDING = paths.DATA / "landing" / "cis"

ESTUDIOS = {
    "3126": {"eleccion": "02-201512", "anterior": "02-201111", "titulo": "Postelectoral elecciones generales 2015. Panel (2ª fase)",
             "modo": "presencial", "campo": "07/01/2016–19/03/2016", "afijacion": "no proporcional", "ponderacion": "PESO",
             "url": "https://www.cis.es/es/estudios/postelectoral-elecciones-generales-2015.-panel-2-fase-",
             "vars": {"voto": "RECUERDO", "voto_anterior": "RECUERDO11", "sexo": "SEXO", "edad": "EDAD", "estudios": "ESTUDIOS",
                      "sitlab": "P63", "ideologia": "P35", "tamuni": "TAMUNI", "ccaa": "CCAA", "peso": "PESO"}},
    "3145": {"eleccion": "02-201606", "anterior": "02-201512", "titulo": "Postelectoral elecciones generales 2016",
             "modo": "presencial", "campo": "02/07/2016–21/07/2016", "afijacion": "proporcional", "ponderacion": "no procede",
             "url": "https://www.cis.es/es/estudios/postelectoral-elecciones-generales-2016",
             "vars": {"voto": "RECUERDO16", "voto_anterior": "RECUERDO15", "sexo": "P47", "edad": "P48", "estudios": "ESTUDIOS",
                      "sitlab": "P60", "ideologia": "P35", "tamuni": "TAMUNI", "ccaa": "CCAA", "peso": None}},
    "3248": {"eleccion": "02-201904", "anterior": "02-201606", "titulo": "Postelectoral elecciones generales 2019",
             "modo": "presencial", "campo": "10/05/2019–25/05/2019", "afijacion": "proporcional", "ponderacion": "no procede",
             "url": "https://www.cis.es/es/estudios/postelectoral-elecciones-generales-2019",
             "vars": {"voto": "P23R", "voto_anterior": "RECUERDO16", "sexo": "P41", "edad": "P42", "estudios": "ESTUDIOS",
                      "sitlab": "P50", "ideologia": "P32", "tamuni": "TAMUNI", "ccaa": "CCAA", "peso": None}},
    "3269": {"eleccion": "02-201911", "anterior": "02-201904", "titulo": "Barómetro de diciembre 2019. Postelectoral elecciones generales 2019",
             "modo": "presencial", "campo": "diciembre de 2019", "afijacion": "no proporcional", "ponderacion": "PESO",
             "url": "https://www.cis.es/es/estudios/barometro-de-diciembre-2019.-postelectoral-elecciones-generales-2019",
             "vars": {"voto": "B22R", "voto_anterior": "RECUERDO", "sexo": "C9", "edad": "C10", "estudios": "ESTUDIOS",
                      "sitlab": "C15", "ideologia": "C3", "tamuni": "TAMUNI", "ccaa": "CCAA", "peso": "PESO"}},
    "3420": {"eleccion": "02-202307", "anterior": "02-201911", "titulo": "Barómetro de septiembre 2023. Postelectoral elecciones generales 2023",
             "modo": "telefónica (CATI)", "campo": "01/09/2023–12/09/2023", "afijacion": "no proporcional", "ponderacion": "PESO",
             "url": "https://www.cis.es/es/estudios/barometro-de-septiembre-2023.-postelectoral-elecciones-generales-2023",
             "vars": {"voto": "RECUERDO1", "voto_anterior": "RECUERDO", "sexo": "SEXO", "edad": "EDAD", "estudios": "ESTUDIOS",
                      "sitlab": "SITLAB", "ideologia": "ESCIDEOL", "tamuni": "TAMUNI", "ccaa": "CCAA", "peso": "PESO"}},
}

# etiqueta del CIS → familia política de Atlas (misma tabla de familias que los resultados oficiales)
REGLAS = [
    (r"^(no vot|abstenci)", "Abstención"),
    (r"^(en blanco|blanco|nulo|voto nulo)", "Blanco o nulo"),
    (r"^no ten[ií]a edad", "Nuevos votantes"),
    (r"^(no recuerda|n\.?c\.?|no ten[ií]a|n\.?s\.?)", None),
    (r"^psoe", "PSOE"), (r"^pp$", "PP"), (r"^vox", "Vox"), (r"^sumar", "Sumar"),
    (r"^(unidas podemos|unidos podemos|podemos|en com[uú] podem|en com[uú]n-u|comprom[ií]s-podemos|en marea)", "Podemos y confluencias"),
    (r"^(iu|izquierda unida)", "IU"), (r"^(c.?s|ciudadanos)", "Ciudadanos"), (r"^upyd", "UPyD"),
    (r"^erc", "ERC"), (r"^(junts|jxcat|cdc|convergència|converg|ciu|dil)", "Convergència / Junts"),
    (r"^eaj-pnv|^pnv", "PNV"), (r"^eh bildu|^bildu", "EH Bildu"), (r"^bng", "BNG"),
    (r"^(cca|cc-pnc|cca-nc|cc )", "Coalición Canaria"), (r"^na\+", "NA+ (coalición UPN-PP-Cs)"), (r"^upn", "UPN"),
    (r"^m[aá]s pa[ií]s", "Más País"), (r"^(m[aáé]s comprom|comprom[ií]s)", "Compromís"), (r"^prc", "PRC"),
    (r"^teruel", "Teruel Existe"), (r"^cup", "CUP"), (r"^pacma", "PACMA"),
    (r"^(otro|otros)", "Otros"),
]
SEXO = {1: "Hombre", 2: "Mujer"}
ESTUD = {1: "Sin estudios", 2: "Primaria", 3: "Secundaria 1ª etapa", 4: "Secundaria 2ª etapa", 5: "FP", 6: "Superiores"}
SITLAB = {1: "Trabaja", 2: "Jubilado/a o pensionista", 3: "Jubilado/a o pensionista", 4: "En paro", 5: "En paro",
          6: "Estudiante", 7: "Trabajo doméstico no remunerado", 8: "Otra situación"}
TAMUNI = {1: "≤ 2.000", 2: "2.001–10.000", 3: "10.001–50.000", 4: "50.001–100.000", 5: "100.001–400.000",
          6: "400.001–1.000.000", 7: "> 1.000.000"}
EDADES = [(18, 24, "18–24"), (25, 34, "25–34"), (35, 44, "35–44"), (45, 54, "45–54"), (55, 64, "55–64"), (65, 120, "65 y más")]
IDEO = [(1, 2, "Izquierda (1–2)"), (3, 4, "Centro-izquierda (3–4)"), (5, 6, "Centro (5–6)"), (7, 8, "Centro-derecha (7–8)"), (9, 10, "Derecha (9–10)")]


def familia(etiqueta: str | None):
    if etiqueta is None:
        return None
    e = etiqueta.strip().lower()
    for pat, fam in REGLAS:
        if re.match(pat, e):
            return fam
    return "Otros"


# ───────────── lectura del formato ASCII + sintaxis SPSS (estudios sin .sav) ─────────────
def leer_sintaxis(es: Path, da: Path, variables: list[str]) -> tuple[pd.DataFrame, dict]:
    txt = es.read_bytes().decode("latin-1")
    bloque = txt[txt.index("DATA LIST"):]
    bloque = bloque[:bloque.index("\n.")] if "\n." in bloque else bloque
    pos = {}
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s+(\d+)(?:-(\d+))?(?:\((\d+)\))?", bloque):
        n, a, b, dec = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)), m.group(4)
        if n.upper() not in ("FILE",):
            pos[n.upper()] = (a, b, int(dec) if dec else 0)
    filas = da.read_bytes().decode("latin-1").splitlines()
    datos = {}
    for v in variables:
        a, b, dec = pos[v.upper()]
        col = []
        for f in filas:
            s = f[a - 1:b].strip()
            if not s:
                col.append(np.nan)
                continue
            s = s.replace(",", ".")  # el CIS puede grabar decimales con coma (configuración regional)
            x = float(s)
            col.append(x / 10 ** dec if dec and "." not in s else x)
        datos[v] = col
    etiquetas = {}
    vl = txt[txt.upper().index("VALUE LABELS"):] if "VALUE LABELS" in txt.upper() else ""
    for m in re.finditer(r"/([A-Za-z0-9_]+)\s*\n((?:\s*-?\d+\s+'(?:[^']|'')*'\s*)+)", vl):
        etiquetas[m.group(1).upper()] = {float(k): lab.replace("''", "'").strip()
                                         for k, lab in re.findall(r"(-?\d+)\s+'((?:[^']|'')*)'", m.group(2))}
    return pd.DataFrame(datos), etiquetas


def leer_estudio(cod: str) -> pd.DataFrame:
    cfg = ESTUDIOS[cod]
    carpeta = LANDING / f"MD{cod}"
    vs = {k: v for k, v in cfg["vars"].items() if v}
    sav = carpeta / f"{cod}.sav"
    if sav.exists():
        import pyreadstat
        df, meta = pyreadstat.read_sav(str(sav), usecols=list(vs.values()))
        etiquetas = {k.upper(): v for k, v in meta.variable_value_labels.items()}
    else:
        df, etiquetas = leer_sintaxis(carpeta / f"ES{cod}", carpeta / f"DA{cod}", list(vs.values()))
    df.columns = [c.upper() for c in df.columns]
    lab = lambda var: df[var.upper()].map(lambda x: etiquetas.get(var.upper(), {}).get(x) if pd.notna(x) else None)
    out = pd.DataFrame({"estudio": cod, "eleccion": cfg["eleccion"], "eleccion_anterior": cfg["anterior"]}, index=df.index)
    out["voto_cis"] = lab(vs["voto"])
    out["voto"] = out.voto_cis.map(familia)
    out["voto_anterior_cis"] = lab(vs["voto_anterior"])
    out["voto_anterior"] = out.voto_anterior_cis.map(familia)
    out["sexo"] = df[vs["sexo"].upper()].map(SEXO)
    edad = pd.to_numeric(df[vs["edad"].upper()], errors="coerce")
    out["edad"] = edad.where((edad >= 18) & (edad < 99))
    out["grupo_edad"] = pd.cut(out.edad, [17, 24, 34, 44, 54, 64, 120], labels=[e[2] for e in EDADES]).astype(object)
    out["estudios"] = df[vs["estudios"].upper()].map(ESTUD)
    out["sitlab"] = df[vs["sitlab"].upper()].map(SITLAB)
    ide = pd.to_numeric(df[vs["ideologia"].upper()], errors="coerce")
    out["ideologia"] = ide.where((ide >= 1) & (ide <= 10))
    out["grupo_ideologia"] = pd.cut(out.ideologia, [0, 2, 4, 6, 8, 10], labels=[e[2] for e in IDEO]).astype(object)
    out["tamuni"] = df[vs["tamuni"].upper()].map(TAMUNI)
    out["ccaa"] = pd.to_numeric(df[vs["ccaa"].upper()], errors="coerce").map(lambda c: f"{int(c):02d}" if pd.notna(c) else None)
    out["peso"] = pd.to_numeric(df[vs["peso"].upper()], errors="coerce") if vs.get("peso") else 1.0
    out["peso"] = out.peso.fillna(1.0)
    return out


def construir() -> pd.DataFrame:
    tablas, meta = [], {}
    for cod, cfg in ESTUDIOS.items():
        z = LANDING / f"MD{cod}.zip"
        if not z.exists():
            print(f"falta {z.name}; se omite")
            continue
        d = leer_estudio(cod)
        tablas.append(d)
        meta[cod] = {k: v for k, v in cfg.items() if k != "vars"} | {
            "variables_origen": cfg["vars"], "n": int(len(d)), "sha256_zip": hashlib.sha256(z.read_bytes()).hexdigest(),
            "voto_valido": int(d.voto.notna().sum()), "sin_respuesta_voto": int(d.voto.isna().sum()),
            "etiquetas_sin_familia": sorted(set(d.loc[d.voto == "Otros", "voto_cis"].dropna()))}
    df = pd.concat(tablas, ignore_index=True)
    destino = paths.DATA / "gold"
    df.to_parquet(destino / "cis_postelectorales.parquet", index=False)
    (destino / "cis_estudios.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(df):,} entrevistas en {len(meta)} estudios")
    for cod, m in meta.items():
        print(f"  {cod} {m['eleccion']}: n={m['n']:,}  voto válido={m['voto_valido']:,}  'Otros' de: {m['etiquetas_sin_familia'][:6]}")
    return df


if __name__ == "__main__":
    construir()
