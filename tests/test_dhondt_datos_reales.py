"""El motor D'Hondt debe reproducir los escaños OFICIALES publicados (datos reales)."""
from pathlib import Path

import pytest

from atlas_spain.electoral.dhondt import dhondt
from atlas_spain.electoral.systems import congreso_district
from atlas_spain.ingestion.connectors.euskadi import parse_csv

FIX = Path(__file__).parent / "fixtures"


def _por_territorio(nombre):
    df = parse_csv((FIX / nombre).read_bytes()).fillna({"votos": 0, "escanos": 0})
    for prov, sub in df.groupby("provincia_ine"):
        votos = {r.candidatura: int(r.votos) for r in sub.itertuples()}
        oficiales = {r.candidatura: int(r.escanos) for r in sub.itertuples()}
        yield prov, votos, oficiales, int(sub.blancos.iloc[0])


@pytest.mark.parametrize("prov,votos,oficiales,blancos", list(_por_territorio("euskadi_CirG23_c.csv")))
def test_congreso_2023_euskadi(prov, votos, oficiales, blancos):
    res = congreso_district(votos, blancos, sum(oficiales.values()), prov)
    assert res.seats == oficiales


@pytest.mark.parametrize("prov,votos,oficiales,blancos", list(_por_territorio("euskadi_CirPV24_c.csv")))
def test_parlamento_vasco_2024(prov, votos, oficiales, blancos):
    assert sum(oficiales.values()) == 25
    assert dhondt(votos, 25, threshold=0.03, blank_votes=blancos).seats == oficiales
