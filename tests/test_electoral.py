import math

import pytest

from atlas_spain.electoral import indices as ix
from atlas_spain.electoral.dhondt import dhondt
from atlas_spain.electoral.systems import (
    concejales_por_poblacion, congreso_apportionment, congreso_district, municipal,
    regimen_municipal, senado_provincia,
)


def test_dhondt_ejemplo_clasico():
    r = dhondt({"A": 100_000, "B": 80_000, "C": 30_000, "D": 20_000}, 8)
    assert r.seats == {"A": 4, "B": 3, "C": 1, "D": 0}
    assert not r.unresolved_ties


def test_dhondt_barrera_sobre_validos_incluye_blancos():
    # 3 % de (1000 + 100 blancos) = 33 votos: C (32) queda fuera, aunque 32/1000 > 3 %... no: 3,2 % de candidaturas
    r = dhondt({"A": 600, "B": 368, "C": 32}, 5, threshold=0.03, blank_votes=100)
    assert "C" not in r.eligible
    r2 = dhondt({"A": 600, "B": 368, "C": 32}, 5, threshold=0.03, blank_votes=0)
    assert "C" in r2.eligible


def test_dhondt_desempate_por_votos_totales():
    # Cociente empatado 300: A (600/2) y B (300/1). Gana el de más votos totales (A).
    r = dhondt({"A": 600, "B": 300}, 3)
    assert r.seats == {"A": 2, "B": 1}
    r = dhondt({"A": 600, "B": 300}, 2)
    assert r.seats == {"A": 2, "B": 0}


def test_dhondt_empate_total_se_informa():
    r = dhondt({"A": 500, "B": 500}, 1)
    assert r.unresolved_ties == [["A", "B"]]


def test_dhondt_suma_escanos():
    r = dhondt({"A": 12345, "B": 6789, "C": 4321, "D": 999}, 37, threshold=0.03)
    assert sum(r.seats.values()) == 37


def test_ceuta_mayoria_simple_sin_dhondt():
    r = congreso_district({"A": 10_000, "B": 9_000}, blank=100, seats=1, province="51")
    assert r.seats == {"A": 1, "B": 0}


def test_reparto_congreso_invariantes():
    pops = {f"{i:02d}": 100_000 + i * 37_000 for i in range(1, 51)}
    pops["51"], pops["52"] = 83_000, 85_000
    s = congreso_apportionment(pops)
    assert sum(s.values()) == 350
    assert s["51"] == 1 and s["52"] == 1
    assert all(v >= 2 for k, v in s.items() if k not in ("51", "52"))
    # monotonía: más población nunca da menos escaños
    ordered = sorted((k for k in pops if k not in ("51", "52")), key=pops.get)
    assert all(s[a] <= s[b] for a, b in zip(ordered, ordered[1:]))


@pytest.mark.parametrize("pob,esperado", [
    (80, 3), (100, 3), (101, 5), (250, 5), (999, 7), (1500, 9), (4000, 11), (8000, 13),
    (15000, 17), (30000, 21), (90000, 25),
    (150_000, 27),     # 25 + 1 = 26 (par) -> 27
    # Padrón 1-1-2022 (base de las municipales 2023) y concejales reales elegidos:
    (792_492, 33),     # Valencia: 25 + 7 = 32 (par) -> 33
    (681_998, 31),     # Sevilla: 25 + 6 = 31
    (1_636_193, 41),   # Barcelona: 25 + 16 = 41
    (3_280_782, 57),   # Madrid: 25 + 32 = 57
])
def test_concejales_lore_179(pob, esperado):
    assert concejales_por_poblacion(pob) == esperado


def test_regimen_municipal():
    assert regimen_municipal(50) == "concejo_abierto"
    assert regimen_municipal(200) == "listas_abiertas_mayoritario"
    assert regimen_municipal(5000) == "dhondt_listas_cerradas"
    with pytest.raises(ValueError):
        municipal({"A": 100}, 0, 200)


def test_municipal_barrera_5():
    r = municipal({"A": 5000, "B": 4000, "C": 480}, blank=100, poblacion=12_000)
    assert sum(r.seats.values()) == 17
    assert r.seats["C"] == 0  # 480 < 5 % de 9580


def test_senado_candidatos_individuales():
    assert senado_provincia({"x": 10, "y": 30, "z": 20, "w": 5, "v": 1}) == ["y", "z", "x", "w"]


def test_indices():
    assert math.isclose(ix.effective_number_of_parties({"A": 50, "B": 50}), 2.0)
    assert math.isclose(ix.fragmentation_rae({"A": 50, "B": 50}), 0.5)
    assert math.isclose(ix.margin({"A": 60, "B": 40}), 0.2)
    assert math.isclose(ix.competitiveness({"A": 60, "B": 40}), 0.8)
    assert math.isclose(ix.pedersen_volatility({"A": 60, "B": 40}, {"A": 40, "B": 40, "C": 20}), 0.2)
    assert ix.gallagher({"A": 50, "B": 50}, {"A": 1, "B": 1}) == 0
    assert ix.wasted_votes({"A": 10, "B": 5}, {"A": 1}) == 5
    assert math.isclose(ix.butler_swing((0.40, 0.35), (0.38, 0.39)), -0.03)
