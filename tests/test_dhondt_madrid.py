"""Asamblea de Madrid: D'Hondt con barrera del 5 % reproduce los escaños oficiales (datos reales)."""
from pathlib import Path

import pandas as pd
import pytest

from atlas_spain.electoral.dhondt import dhondt

DF = pd.read_csv(Path(__file__).parent / "fixtures" / "cmadrid_asamblea_territorio.csv")


@pytest.mark.parametrize("anyo", sorted(DF.anyo.unique()))
def test_asamblea_madrid(anyo):
    t = DF[DF.anyo == anyo]
    if t.escanos.isna().all():
        pytest.skip("la fuente no publica escaños para esta convocatoria")
    votos = {r.candidatura: int(r.votos) for r in t.itertuples() if r.candidatura != "Resto de partidos"}
    oficiales = {r.candidatura: int(r.escanos) for r in t.itertuples()
                 if r.candidatura != "Resto de partidos" and pd.notna(r.escanos)}
    res = dhondt(votos, int(t.escanos.sum()), threshold=0.05, threshold_base=int(t.validos.iloc[0]))
    assert all(res.seats.get(k, 0) == oficiales.get(k, 0) for k in set(votos) | set(oficiales))
