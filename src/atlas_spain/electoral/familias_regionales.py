"""Asignación complementaria de candidaturas a familias políticas por reglas de nombre.

La tabla principal (dbt/seeds/party_families.csv, revisada a mano) lista siglas por convocatoria. Muchas candidaturas
quedaban en «Otros» por variantes de siglas (PSN-PSOE, U.P.N., IU-CYL…) o por ser partidos regionales sin familia
(Teruel Existe, Chunta, Geroa Bai, Foro…). Este módulo propone una familia para las candidaturas NO listadas en la tabla
principal, aplicando reglas explícitas sobre siglas y denominación, y escribe dbt/seeds/party_families_extra.csv con la
regla que justifica cada fila. Las listas locales sin regla siguen en «Otros».

    python -m atlas_spain.electoral.familias_regionales [--revisar]
"""
from __future__ import annotations

import re
import sys
import unicodedata

import duckdb
import pandas as pd

from atlas_spain import paths

SEED = paths.ROOT / "dbt" / "seeds" / "party_families_extra.csv"

# (familia, patrón sobre «SIGLAS | DENOMINACIÓN» normalizado, desde_año, hasta_año). Se aplica la primera que encaja.
REGLAS = [
    # variantes de siglas de familias ya existentes
    ("Sumar", r"\bSUMAR\b", 2023, 2099),
    ("Más País", r"\bM(AS)? PAIS\b", 2019, 2019),
    ("Podemos y confluencias", r"\bPODEM(OS)?\b", 2014, 2023),
    ("Més per Mallorca", r"\bPSM\b|MES PER MALLORCA|UNITAT PER LES ILLES|^MES(-APIB)? \|", 1977, 2099),
    ("PSOE", r"\bPSOE\b|PARTIDO SOCIALISTA OBRERO ESPA|PARTIDO SOCIALISTA DE NAVARRA", 1977, 2099),
    ("Vox", r"\bVOX\b", 2013, 2099),
    ("Ciudadanos", r"\bCIUTADANS\b|\bCIUDADANOS-PARTIDO|\bC'?S\b.*CIUDADANOS|CIUDADANOS \(|^C'?S \|", 2006, 2099),
    ("IU", r"^I\.?U\.?\b|IZQUIERDA UNIDA|EZKER BATUA|ESQUERRA UNIDA", 1986, 2099),
    ("UPN", r"UNION DEL PUEBLO NAVARRO|^U\.?P\.?N\.? \|", 1979, 2099),
    ("PRC", r"PARTIDO REGIONALISTA DE CANTABRIA|^P\.?R\.?C\.? \|", 1977, 2099),
    ("PAR", r"PARTIDO ARAGONES|CANDIDATURA ARAGONESA INDEPENDIENTE DE CENTRO", 1977, 2099),
    ("Coalición Canaria", r"COALICION CANARIA|AGRUPACIONES? INDEPENDIENTES? DE CANARIAS|AGRUPACION TINERFENA|^A\.?I\.?C\.? \||^ATI \|", 1983, 2099),
    ("BNG", r"BLOQUE NACIONAL[- ]POPULAR GALEGO|^BN-?PG \|", 1977, 2099),
    ("Compromís", r"\bCOMPROMIS\b|BLOC NACIONALISTA VALENCIA|PRIMAVERA EUROPEA", 1990, 2099),
    ("CDS", r"CENTRO DEMOCRATICO Y SOCIAL", 1982, 2099),
    ("AP / Coalición Popular", r"^AP-PL \||ALIANZA POPULAR", 1977, 1988),
    ("Convergència / Junts", r"UNIO DEL CENTRE I LA DEM", 1977, 1977),
    ("Izquierda abertzale (HB / EH)", r"INIZIATIBA INTERNAZIONALISTA|ACCION NACIONALISTA VASCA|EUSKO ABERTZALE EKINTZA", 2007, 2010),
    # familias regionales nuevas
    ("Teruel Existe", r"TERUEL EXISTE|ARAGON EXISTE|ESPANA OLVIDADA EXISTE|^EXISTE \|", 2019, 2099),
    ("Soria ¡Ya!", r"SORIA ?\W?YA\W?", 2019, 2099),
    ("Por Ávila", r"POR AVILA|^XAV \|", 2019, 2099),
    ("UPL", r"UNION DEL PUEBLO LEONES|^U\.?P\.?L\.? \|", 1986, 2099),
    ("Nueva Canarias", r"NUEVA CANARIAS|NUEVA GRAN CANARIA|^NCA? \||^NC-", 2005, 2099),
    ("Chunta Aragonesista", r"CHUNTA ARAGONESISTA|^CHA \|", 1986, 2099),
    ("Geroa Bai", r"GEROA BAI|NAFARROA BAI|^NA-?BAI", 2003, 2099),
    ("Foro Asturias", r"FORO DE CIUDADANOS|FORO ASTURIAS|^FAC \|", 2011, 2099),
    ("Coalición por Melilla", r"COALICION POR MELILLA|^CPM \|", 1995, 2099),
    ("Caballas", r"CABALLAS", 2011, 2099),
    ("Euskadiko Ezkerra", r"EUSKADIKO EZ", 1977, 1993),
    ("Eusko Alkartasuna", r"EUSKO ALKARTASUNA|HERRIEN EUROPAREN ALDE|EUROPA DE LOS PUEBLOS", 1987, 2010),
    ("Aralar", r"\bARALAR\b", 2001, 2011),
    ("Unidad Alavesa", r"UNIDAD ALAVESA", 1989, 2005),
    ("UPCA", r"UNION PARA EL PROGRESO DE CANTABRIA", 1990, 1999),
    ("Unió Valenciana", r"UNIO VALENCIANA", 1982, 2011),
    ("Unió Mallorquina", r"UNIO MALLORQUINA", 1982, 2011),
    ("Partido Riojano", r"PARTIDO RIOJANO", 1982, 2099),
    ("PSP", r"PARTIDO SOCIALISTA POPULAR", 1977, 1978),
    ("UPC", r"UNION DEL PUEBLO CANARIO", 1977, 1983),
    ("Coalición Galega", r"COALICION GALEGA", 1984, 1990),
    ("GIL", r"GRUPO INDEPENDIENTE LIBERAL", 1990, 2005),
    ("Unión Nacional", r"PARTIDO UNION NACIONAL|^UN \| UNION NACIONAL", 1979, 1979),
]
EXCLUIR = r"\bINDEP(ENDIENTES?)?\b \||^RESTO \||AGRUP\.?\s*DE ELECTORES|HISTORICO|^PSOE ?-? ?\(?H\)? \|"


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s if isinstance(s, str) else "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", s).strip()


def proponer() -> pd.DataFrame:
    con = duckdb.connect(str(paths.DATA / "warehouse" / "atlas.duckdb"), read_only=True)
    df = con.execute("""
        select r.election_id, r.agrupacion_siglas, any_value(r.agrupacion_denominacion) as den,
               max(case when r.geo_level = 'provincia' then r.vote_share end) as max_prov, sum(case when r.geo_level='provincia' then r.escanos end) as esc
        from gold.results_by_group r
        left join main.party_families f on f.election_id = r.election_id and f.agrupacion_siglas = r.agrupacion_siglas
        where f.familia is null and r.agrupacion_siglas is not null
        group by 1, 2""").df()
    con.close()
    filas = []
    for r in df.itertuples():
        anyo = int(r.election_id[3:7])
        texto = f"{_norm(r.agrupacion_siglas)} | {_norm(r.den)}"
        if re.search(EXCLUIR, texto):
            continue
        for fam, pat, desde, hasta in REGLAS:
            if desde <= anyo <= hasta and re.search(pat, texto):
                filas.append({"election_id": r.election_id, "agrupacion_siglas": r.agrupacion_siglas, "familia": fam,
                              "regla": pat, "denominacion": r.den, "max_prov": r.max_prov, "escanos": r.esc})
                break
    return pd.DataFrame(filas).sort_values(["familia", "election_id", "agrupacion_siglas"])


def escribir(p: pd.DataFrame) -> None:
    p[["election_id", "agrupacion_siglas", "familia", "regla"]].to_csv(SEED, index=False, encoding="utf-8")
    print(f"{len(p):,} filas → {SEED.name}")


if __name__ == "__main__":
    p = proponer()
    if "--revisar" in sys.argv:
        pd.set_option("display.width", 250, "display.max_colwidth", 60, "display.max_rows", 400)
        print(p.groupby("familia").agg(filas=("agrupacion_siglas", "size"), elecciones=("election_id", "nunique"),
                                       max_prov=("max_prov", "max")).sort_values("filas", ascending=False).to_string())
        print(p[p.max_prov.fillna(0) >= 0.03][["election_id", "agrupacion_siglas", "denominacion", "familia", "max_prov"]].to_string())
    else:
        escribir(p)
