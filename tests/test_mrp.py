"""MRP de votantes por provincia: calibración, marco censal y coherencia de las estimaciones publicadas."""
import json

import numpy as np
import pytest

from atlas_spain import paths
from atlas_spain.encuestas import mrp

SALIDA = paths.DATA / "gold" / "mrp"


def test_calibrar_reproduce_el_objetivo():
    rng = np.random.default_rng(1)
    n = rng.uniform(100, 5000, 40)
    p = rng.dirichlet(np.ones(5), 40)
    t = np.array([0.30, 0.25, 0.20, 0.0, 0.25])
    q = mrp.calibrar(n, p, t)
    assert np.allclose(q.sum(1), 1)
    assert np.allclose((n[:, None] * q).sum(0) / n.sum(), t, atol=1e-6)
    assert np.all(q[:, 3] == 0)  # sin candidatura → cero votos en todas las celdas
    # conserva el orden relativo entre celdas (es un desplazamiento logístico, no una reasignación arbitraria)
    assert np.corrcoef(np.log(p[:, 0] / p[:, 1]), np.log(q[:, 0] / q[:, 1]))[0, 1] > 0.999


@pytest.mark.skipif(not mrp.CENSO_CSV.exists(), reason="sin la tabla 66601 del INE")
def test_marco_censal():
    m = mrp.marco(2023)
    assert m.prov.nunique() == 52
    assert 33e6 < m.n.sum() < 37e6  # españoles de 18+ residentes (el censo electoral CER ronda los 35 millones)
    assert set(m.edad) == set(mrp.EDADES) and set(m.estudios) == set(mrp.ESTUDIOS)
    assert set(m.sitlab) == set(mrp.SITLABS) and set(m.tamuni) == set(mrp.TAMANOS)
    # el marco ampliado conserva los totales del censo por provincia, sexo, edad y estudios
    b = mrp.marco_basico(2023).groupby(["prov", "sexo", "edad", "estudios"]).n.sum()
    assert np.allclose(m.groupby(["prov", "sexo", "edad", "estudios"]).n.sum().reindex(b.index).fillna(0), b, rtol=1e-3, atol=1)


def _cargar(eleccion):
    f = SALIDA / f"{eleccion}.json"
    if not f.exists():
        pytest.skip("estimaciones MRP no generadas")
    return json.loads(f.read_text(encoding="utf-8"))


@pytest.mark.parametrize("eleccion", ["02-201512", "02-202307"])
def test_estimaciones_coherentes(eleccion):
    from atlas_spain.stats.panel import Panel
    d = _cargar(eleccion)
    P = Panel(paths.DATA / "gold" / "stat_panel.npz")
    obj = mrp.objetivos(P, eleccion, d["partidos"])
    provs = [u for u in d["unidades"] if u["nivel"] == "provincia"]
    assert len(provs) == 52
    for u in provs:
        # cada provincia reproduce su resultado oficial (abstención y voto por partido, sobre el censo)
        assert np.allclose(u["voto"], obj[u["id"][-2:]] * 100, atol=0.06)
        for j, (p, lo, hi) in enumerate(u["comp"]):
            if u["voto"][j] < 0.3:
                continue
            i = 0
            for cs in d["dims"].values():
                assert sum(p[i:i + len(cs)]) == pytest.approx(100, abs=0.5)
                i += len(cs)
            assert all(a <= b + 0.05 for a, b in zip(lo, hi))
    # la suma de las provincias es España
    es = next(u for u in d["unidades"] if u["id"] == "ES")
    assert es["poblacion"] == pytest.approx(sum(u["poblacion"] for u in provs), rel=1e-3)


def test_validacion_publicada():
    f = SALIDA / "indice.json"
    if not f.exists():
        pytest.skip("estimaciones MRP no generadas")
    v = json.loads(f.read_text(encoding="utf-8"))["validacion"]
    assert v and all(x["comparaciones"] > 0 for x in v)
