"""Parser de los ficheros DAT de ancho fijo de Infoelectoral (Ministerio del Interior).

Diseño de registro según la documentación oficial de los ficheros de resultados
(posiciones 1-based, inclusivas), contrastado con el paquete abierto
hmeleiro/infoelectoral. Codificación ISO-8859-1 (1 byte = 1 carácter).

Ficheros dentro de cada ZIP: NNTTAAMM.DAT
    NN = tipo de fichero (01 control, 02 identificación, 03 candidaturas,
         04 candidatos, 05/06 municipios, 07/08 ámbito superior,
         09/10 mesas, 11/12 municipios < 250 hab. — solo municipales)
    TT = tipo de elección (01 referéndum, 02 Congreso, 03 Senado,
         04 municipales, 06 cabildos, 07 Parlamento Europeo)
    AA = año (2 dígitos), MM = mes

PRIVACIDAD: del fichero 04 (candidatos) se DESCARTAN el DNI y la fecha de
nacimiento. Solo se conservan nombre, sexo, orden en la lista y condición de
electo, que son datos publicados en el BOE para cargos públicos.
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

# (nombre, inicio, fin, tipo) — tipo: 's' texto, 'i' entero
Layout = list[tuple[str, int, int, str]]

_HEAD = [("tipo_eleccion", 1, 2, "s"), ("anno", 3, 6, "s"), ("mes", 7, 8, "s")]

LAYOUTS: dict[str, Layout] = {
    "03": _HEAD + [
        ("codigo_candidatura", 9, 14, "s"), ("siglas", 15, 64, "s"), ("denominacion", 65, 214, "s"),
        ("codigo_candidatura_provincial", 215, 220, "s"),
        ("codigo_candidatura_autonomica", 221, 226, "s"),
        ("codigo_candidatura_nacional", 227, 232, "s"),
    ],
    "04": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_provincia", 10, 11, "s"), ("codigo_distrito_electoral", 12, 12, "s"),
        ("codigo_municipio_o_senador", 13, 15, "s"), ("codigo_candidatura", 16, 21, "s"),
        ("orden_candidato", 22, 24, "i"), ("tipo_candidato", 25, 25, "s"),
        ("nombre", 26, 50, "s"), ("apellido_1", 51, 75, "s"), ("apellido_2", 76, 100, "s"),
        ("sexo", 101, 101, "s"),
        # 102-109 fecha de nacimiento y 110-119 DNI: NO se leen (privacidad)
        ("electo", 120, 120, "s"),
    ],
    "05": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_ccaa_mir", 10, 11, "s"), ("codigo_provincia", 12, 13, "s"),
        ("codigo_municipio", 14, 16, "s"), ("codigo_distrito", 17, 18, "s"),
        ("nombre_municipio", 19, 118, "s"),
        ("codigo_distrito_electoral", 119, 119, "s"), ("codigo_partido_judicial", 120, 122, "s"),
        ("codigo_diputacion", 123, 125, "s"), ("codigo_comarca", 126, 128, "s"),
        ("poblacion_derecho", 129, 136, "i"), ("numero_mesas", 137, 141, "i"),
        ("censo_ine", 142, 149, "i"), ("censo_escrutinio", 150, 157, "i"),
        ("censo_cere", 158, 165, "i"), ("votantes_cere", 166, 173, "i"),
        ("participacion_1", 174, 181, "i"), ("participacion_2", 182, 189, "i"),
        ("votos_blancos", 190, 197, "i"), ("votos_nulos", 198, 205, "i"),
        ("votos_candidaturas", 206, 213, "i"), ("numero_escanos", 214, 216, "i"),
        ("datos_oficiales", 233, 233, "s"),
    ],
    "06": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_provincia", 10, 11, "s"), ("codigo_municipio", 12, 14, "s"),
        ("codigo_distrito", 15, 16, "s"), ("codigo_candidatura", 17, 22, "s"),
        ("votos", 23, 30, "i"), ("escanos", 31, 33, "i"),
    ],
    "07": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_ccaa_mir", 10, 11, "s"), ("codigo_provincia", 12, 13, "s"),
        ("codigo_distrito_electoral", 14, 14, "s"), ("nombre_ambito", 15, 64, "s"),
        ("poblacion_derecho", 65, 72, "i"), ("numero_mesas", 73, 77, "i"),
        ("censo_ine", 78, 85, "i"), ("censo_escrutinio", 86, 93, "i"),
        ("censo_cere", 94, 101, "i"), ("votantes_cere", 102, 109, "i"),
        ("participacion_1", 110, 117, "i"), ("participacion_2", 118, 125, "i"),
        ("votos_blancos", 126, 133, "i"), ("votos_nulos", 134, 141, "i"),
        ("votos_candidaturas", 142, 149, "i"), ("numero_escanos", 150, 155, "i"),
        ("votos_afirmativos", 156, 163, "i"), ("votos_negativos", 164, 171, "i"),
        ("datos_oficiales", 172, 172, "s"),
    ],
    "08": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_ccaa_mir", 10, 11, "s"), ("codigo_provincia", 12, 13, "s"),
        ("codigo_distrito_electoral", 14, 14, "s"), ("codigo_candidatura", 15, 20, "s"),
        ("votos", 21, 28, "i"), ("escanos", 29, 33, "i"),
    ],
    "09": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_ccaa_mir", 10, 11, "s"), ("codigo_provincia", 12, 13, "s"),
        ("codigo_municipio", 14, 16, "s"), ("codigo_distrito", 17, 18, "s"),
        ("codigo_seccion", 19, 22, "s"), ("codigo_mesa", 23, 23, "s"),
        ("censo_ine", 24, 30, "i"), ("censo_cera", 31, 37, "i"), ("censo_cere", 38, 44, "i"),
        ("votantes_cere", 45, 51, "i"), ("participacion_1", 52, 58, "i"),
        ("participacion_2", 59, 65, "i"), ("votos_blancos", 66, 72, "i"),
        ("votos_nulos", 73, 79, "i"), ("votos_candidaturas", 80, 86, "i"),
        ("datos_oficiales", 101, 101, "s"),
    ],
    "10": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_ccaa_mir", 10, 11, "s"), ("codigo_provincia", 12, 13, "s"),
        ("codigo_municipio", 14, 16, "s"), ("codigo_distrito", 17, 18, "s"),
        ("codigo_seccion", 19, 22, "s"), ("codigo_mesa", 23, 23, "s"),
        ("codigo_candidatura", 24, 29, "s"), ("votos", 30, 36, "i"),
    ],
    "11": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_ccaa_mir", 10, 11, "s"), ("codigo_provincia", 12, 13, "s"),
        ("codigo_municipio", 14, 16, "s"), ("nombre_municipio", 17, 116, "s"),
        ("codigo_partido_judicial", 117, 119, "s"), ("codigo_diputacion", 120, 122, "s"),
        ("codigo_comarca", 123, 125, "s"), ("poblacion_derecho", 126, 128, "i"),
        ("numero_mesas", 129, 130, "i"), ("censo_ine", 131, 133, "i"),
        ("censo_escrutinio", 134, 136, "i"), ("censo_cere", 137, 139, "i"),
        ("votantes_cere", 140, 142, "i"), ("participacion_1", 143, 145, "i"),
        ("participacion_2", 146, 148, "i"), ("votos_blancos", 149, 151, "i"),
        ("votos_nulos", 152, 154, "i"), ("votos_candidaturas", 155, 157, "i"),
        ("numero_escanos", 158, 159, "i"), ("datos_oficiales", 160, 160, "s"),
    ],
    # Municipios < 250 hab.: listas abiertas. Una fila por CANDIDATO (votos individuales);
    # no son "votos a candidatura" comparables con los de listas cerradas.
    "12": _HEAD + [
        ("vuelta", 9, 9, "s"), ("codigo_provincia", 10, 11, "s"), ("codigo_municipio", 12, 14, "s"),
        ("codigo_candidatura", 15, 20, "s"), ("votos", 21, 23, "i"), ("escanos", 24, 25, "i"),
    ],
}

FILE_RE = re.compile(r"(?:^|/)(\d{2})(\d{2})(\d{2})(\d{2})\.DAT$", re.IGNORECASE)

ELECTION_TYPES = {
    "01": "referendum", "02": "congreso", "03": "senado",
    "04": "municipales", "06": "cabildos", "07": "europeas",
}


def parse_lines(lines: list[str], file_type: str) -> pd.DataFrame:
    layout = LAYOUTS[file_type]
    data: dict[str, list] = {name: [] for name, *_ in layout}
    for line in lines:
        if not line.strip():
            continue
        for name, a, b, kind in layout:
            raw = line[a - 1:b]
            if kind == "i":
                raw = raw.strip()
                data[name].append(int(raw) if raw.lstrip("-").isdigit() else None)
            else:
                data[name].append(raw.strip())
    df = pd.DataFrame(data)
    # Algunos ficheros traen líneas de relleno (año 0000): no son registros electorales.
    if "anno" in df:
        df = df[df["anno"].str.match(r"^(19|20)\d\d$")].reset_index(drop=True)
    for name, *_, kind in layout:
        if kind == "i":
            df[name] = df[name].astype("Int64")
    return df


def parse_bytes(content: bytes, file_type: str) -> pd.DataFrame:
    text = content.decode("iso-8859-1")
    return parse_lines(text.splitlines(), file_type)


def parse_zip(zip_bytes: bytes) -> dict[str, pd.DataFrame]:
    """Devuelve {tipo_fichero: DataFrame} para todos los DAT reconocidos del ZIP."""
    out: dict[str, list[pd.DataFrame]] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            m = FILE_RE.search(info.filename)
            if not m:
                continue
            ftype = m.group(1)
            if ftype not in LAYOUTS:
                continue
            df = parse_bytes(zf.read(info), ftype)
            df["_fichero"] = info.filename
            out.setdefault(ftype, []).append(df)
    return {k: pd.concat(v, ignore_index=True) for k, v in out.items()}
