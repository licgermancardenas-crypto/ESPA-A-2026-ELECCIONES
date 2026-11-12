"""Encuestas nacionales de intención de voto (generales 2026) desde Wikipedia.

Fuente SECUNDARIA: «Opinion polling for the 2026 Spanish general election» (en.wikipedia.org), descargada
con la API (`action=parse&prop=wikitext`) y guardada en data/landing/encuestas_2026/. Cada fila conserva
la URL de la publicación original que cita Wikipedia; mientras no se coteje con esa publicación, la
encuesta queda marcada `verificacion = "pendiente"`.

Solo se toman las tablas de «Voting intention estimates». Se guardan la estimación de voto (%), la
horquilla de escaños si se publica, el instituto, el medio, las fechas de campo y el tamaño muestral.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from ..paths import LANDING

DIR = LANDING / "encuestas_2026"
WIKITEXT = DIR / "wiki_polls_en.wikitext"
PAGINA = "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Spanish_general_election"

MESES = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

# Etiqueta de columna en Wikipedia -> clave interna de partido
ETIQUETAS = {
    "PP": "PP", "PSOE": "PSOE", "Vox": "VOX", "FA": "FA", "FV": "FV", "Sumar": "SUMAR",
    "ERC": "ERC", "Junts": "JUNTS", "EH Bildu": "BILDU", "PNV": "PNV", "BNG": "BNG", "CCa": "CCA",
    "UPN": "UPN", "Adelante Andalucía (2021)": "ADELANTE", "link=Adelante Andalucía (2021)": "ADELANTE", "Podemos": "PODEMOS", "SALF": "SALF",
    "Aliança.cat": "ALIANCA", "Cs": "CS",
}


def _split_top(s: str, sep: str) -> list[str]:
    """Divide por `sep` fuera de [[ ]], {{ }} y <ref>…</ref>."""
    out, buf, prof, i = [], [], 0, 0
    while i < len(s):
        if s.startswith("<ref", i):
            fin = s.find("</ref>", i)
            cierre = s.find("/>", i)
            j = (cierre + 2) if (cierre != -1 and (fin == -1 or cierre < s.find(">", i) + 1)) else \
                (fin + 6 if fin != -1 else len(s))
            buf.append(s[i:j])
            i = j
            continue
        dos = s[i:i + 2]
        if dos in ("[[", "{{"):
            prof += 1
            buf.append(dos)
            i += 2
            continue
        if dos in ("]]", "}}"):
            prof = max(0, prof - 1)
            buf.append(dos)
            i += 2
            continue
        if prof == 0 and s.startswith(sep, i):
            out.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        buf.append(s[i])
        i += 1
    out.append("".join(buf))
    return out


def _celdas(linea: str) -> list[tuple[int, str]]:
    """Celdas de una línea de tabla wiki ('| a || b'), con su colspan."""
    res = []
    for c in _split_top(linea[1:], "||"):
        partes = _split_top(c, "|")
        attrs, cont = (partes[0], "|".join(partes[1:])) if len(partes) > 1 else ("", partes[0])
        if "=" not in attrs and len(partes) > 1 and not re.search(r"\w+\s*=", attrs):
            cont = c  # el primer '|' no separaba atributos
        m = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
        res.append((int(m.group(1)) if m else 1, cont.strip()))
    return res


def _cabecera(lineas: list[str]) -> list[str]:
    cols = []
    for l in lineas:
        if not l.startswith("!"):
            continue
        if "rowspan" in l and "Lead" not in l and "[[" not in l:
            continue
        m = re.findall(r"\|([^|\]]+)\]\]\s*$", l)
        if m:
            cols.append(m[-1].strip())
        elif "link=" in l:
            cols.append(re.search(r"link=([^|\]]+)", l).group(1).strip())
    return cols


def _num(txt: str) -> float | None:
    t = re.sub(r"<ref.*?(</ref>|/>)", "", txt, flags=re.S)
    t = re.sub(r"^\s*\{\{[^}]*\}\}\s*\|", "", t)   # sombreado del ganador: "{{Party shading/X}}| 31.4"
    t = re.sub(r"\{\{efn[^}]*\}\}", "", t)
    t = t.replace("'''", "")
    m = re.match(r"\s*(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else None


def _escanos(txt: str) -> str | None:
    m = re.search(r"text=([\d/–\-]+)\}\}", txt)
    return m.group(1) if m else None


def _fechas(txt: str, anio: int) -> tuple[date | None, date | None]:
    t = re.sub(r"\{\{[^}]*\}\}", "", txt).replace("&ndash;", "–").strip()
    m = re.match(r"(\d{1,2})(?:\s+([A-Z][a-z]{2}))?\s*[–-]\s*(\d{1,2})\s+([A-Z][a-z]{2})(?:\s+(\d{4}))?", t)
    if m:
        d1, m1, d2, m2, y = m.groups()
        y2 = int(y) if y else anio
        mes2 = MESES[m2]
        mes1 = MESES[m1] if m1 else mes2
        y1 = y2 - 1 if mes1 > mes2 else y2
        return date(y1, mes1, int(d1)), date(y2, mes2, int(d2))
    m = re.match(r"(\d{1,2})\s+([A-Z][a-z]{2})(?:\s+(\d{4}))?", t)
    if m:
        d = date(int(m.group(3)) if m.group(3) else anio, MESES[m.group(2)], int(m.group(1)))
        return d, d
    return None, None


def _secciones(bloque: str, anio_defecto: int):
    secs = [(int(s.group(1)), s.group(0).split("\n")[0].strip("= "), s.group(2))
            for s in re.finditer(r"=====(\d{4})[^=\n]*=====\n(.*?)(?=\n=====|\Z)", bloque, flags=re.S)]
    return secs or [(anio_defecto, str(anio_defecto), bloque)]


def parsear(w: str | None = None, anio_defecto: int = 2026, pagina: str = PAGINA) -> pd.DataFrame:
    w = w if w is not None else WIKITEXT.read_text(encoding="utf-8")
    w = w.replace("\r\n", "\n")
    ini = w.find("====Voting intention estimates====")
    fin = w.find("====Voting preferences====")
    bloque = w[ini:fin]
    filas = []
    for anio, nombre_sec, cuerpo in _secciones(bloque, anio_defecto):
        tabla = cuerpo[cuerpo.find("{|"):cuerpo.find("\n|}")]
        bloques = re.split(r"\n\|-[^\n]*", tabla)
        cols = [ETIQUETAS.get(c, c) for c in _cabecera(bloques[1].split("\n") if len(bloques) > 1 else [])]
        cols = [c for c in cols if c != "Lead"]
        for b in bloques[2:]:
            lineas = [l for l in b.split("\n") if l.startswith("|") and not l.startswith("|}")]
            celdas = [c for l in lineas for c in _celdas(l)]
            if len(celdas) < 5:
                continue
            firma_raw = celdas[0][1]
            if "election" in firma_raw and "'''" in firma_raw:
                continue  # fila de resultado electoral, no es encuesta
            url = re.search(r"\|\s*url\s*=\s*([^|}\s]+)", firma_raw)
            firma = re.sub(r"<ref.*?(</ref>|/>)", "", firma_raw, flags=re.S)
            firma = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", firma)
            firma = re.sub(r"\{\{[^}]*\}\}", "", firma).replace("'''", "").strip()
            f_ini, f_fin = _fechas(celdas[1][1], anio)
            muestra = _num(celdas[2][1].replace(",", ""))
            pos, rec = 0, {}
            for span, cont in celdas[4:]:
                if pos >= len(cols):
                    break
                grupo = cols[pos:pos + span]
                v = _num(cont)
                rec[grupo[0]] = v
                for g in grupo[1:]:
                    rec[g] = None
                if span > 1:
                    rec[f"conjunta_{grupo[0]}"] = "+".join(grupo)
                rec[f"esc_{grupo[0]}"] = _escanos(cont)
                pos += span
            instituto, _, medio = firma.partition("/")
            filas.append({
                "instituto": instituto.strip(), "medio": medio.strip() or None,
                "campo_inicio": f_ini, "campo_fin": f_fin,
                "muestra": int(muestra) if muestra else None,
                "seccion_wiki": nombre_sec,
                "fuente_original": url.group(1) if url else None,
                "fuente_secundaria": pagina, "verificacion": "pendiente",
                **rec,
            })
    df = pd.DataFrame(filas)
    return df[df["campo_fin"].notna()].reset_index(drop=True)
