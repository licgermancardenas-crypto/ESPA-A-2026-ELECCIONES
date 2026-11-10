"""Tests del parser de ancho fijo con líneas SINTÉTICAS construidas desde el diseño
de registro. No son datos electorales reales."""

import io
import zipfile

from atlas_spain.parsers.infoelectoral_dat import LAYOUTS, parse_lines, parse_zip


def build_line(file_type: str, values: dict, width: int = 240) -> str:
    buf = [" "] * width
    for name, a, b, kind in LAYOUTS[file_type]:
        if name not in values:
            continue
        n = b - a + 1
        v = str(values[name])
        v = v.rjust(n, "0") if kind == "i" else v.ljust(n)
        buf[a - 1:b] = list(v[:n])
    return "".join(buf).rstrip()


def test_roundtrip_fichero_06():
    vals = {"tipo_eleccion": "02", "anno": "2023", "mes": "07", "vuelta": "1",
            "codigo_provincia": "28", "codigo_municipio": "079", "codigo_distrito": "99",
            "codigo_candidatura": "000123", "votos": 456789, "escanos": 0}
    df = parse_lines([build_line("06", vals)], "06")
    row = df.iloc[0]
    assert row["codigo_provincia"] == "28" and row["codigo_municipio"] == "079"
    assert row["codigo_candidatura"] == "000123"
    assert int(row["votos"]) == 456789


def test_fichero_04_descarta_dni_y_nacimiento():
    line = build_line("04", {"tipo_eleccion": "02", "anno": "2023", "mes": "07", "codigo_provincia": "28",
                             "codigo_candidatura": "000001", "orden_candidato": 1, "tipo_candidato": "T",
                             "nombre": "NOMBRE", "apellido_1": "APELLIDO", "sexo": "M", "electo": "S"})
    # Escribimos un DNI ficticio en 110-119: no debe aparecer en la salida
    line = line.ljust(120)
    line = line[:109] + "99999999X " + line[119:]
    df = parse_lines([line], "04")
    assert "dni" not in df.columns and not any("nacimiento" in c for c in df.columns)
    assert "99999999X" not in df.to_string()
    assert df.iloc[0]["electo"] == "S"


def test_parse_zip_reconoce_nombres():
    l05 = build_line("05", {"tipo_eleccion": "02", "anno": "2023", "mes": "07", "codigo_provincia": "01",
                            "codigo_municipio": "001", "codigo_distrito": "99", "censo_ine": 2000,
                            "votos_blancos": 10, "votos_nulos": 5, "votos_candidaturas": 1500})
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as z:
        z.writestr("02202307_MUNI/05022307.DAT", (l05 + "\r\n").encode("iso-8859-1"))
        z.writestr("LEEME.txt", b"x")
    out = parse_zip(mem.getvalue())
    assert set(out) == {"05"}
    assert int(out["05"].iloc[0]["votos_candidaturas"]) == 1500


def test_descarta_lineas_de_relleno():
    buena = build_line("07", {"tipo_eleccion": "04", "anno": "2003", "mes": "05", "codigo_ccaa_mir": "01",
                              "codigo_provincia": "04", "codigo_distrito_electoral": "9", "votos_candidaturas": 10})
    relleno = build_line("07", {"tipo_eleccion": "04", "anno": "0000", "mes": "31", "codigo_provincia": "00"})
    df = parse_lines([buena, relleno], "07")
    assert len(df) == 1 and df.iloc[0]["anno"] == "2003"
