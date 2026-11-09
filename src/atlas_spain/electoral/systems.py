"""Sistemas electorales españoles: módulos independientes por tipo de elección.

No se aplica una fórmula única a todas las elecciones. Cada función implementa
la norma de su convocatoria y cita el artículo de la LOREG (Ley Orgánica 5/1985)
en el que se basa. Las autonómicas se configuran en config/electoral_systems.yaml
porque cada estatuto/ley electoral autonómica fija sus propias reglas.
"""

from __future__ import annotations

import math
from fractions import Fraction

from atlas_spain.electoral.dhondt import DhondtResult, dhondt

# ───────────────────────── CONGRESO ─────────────────────────
CONGRESO_TOTAL = 350              # art. 162.1
CONGRESO_MIN_PROV = 2             # art. 162.2
CEUTA, MELILLA = "51", "52"       # art. 162.2: un diputado cada una (art. 163.2: mayoría simple)
CONGRESO_THRESHOLD = 0.03         # art. 163.1.a


def congreso_apportionment(population: dict[str, int]) -> dict[str, int]:
    """Reparto de los 350 escaños entre circunscripciones (LOREG art. 162).

    population: población de derecho por código INE de provincia (2 dígitos),
    incluidas '51' (Ceuta) y '52' (Melilla). Debe ser la cifra oficial vigente
    al convocar (Real Decreto de convocatoria).

    Procedimiento (art. 162.3):
      a) cuota de reparto = población total de las provincias peninsulares e
         insulares / 248 (350 - 2×50 mínimos - 2 de Ceuta y Melilla)
      b) cada provincia recibe tantos diputados como enteros resulten de dividir
         su población por la cuota
      c) los restantes se asignan a las provincias con mayores fracciones decimales.
    """
    provs = {k: v for k, v in population.items() if k not in (CEUTA, MELILLA)}
    if len(provs) != 50:
        raise ValueError(f"Se esperaban 50 provincias, hay {len(provs)}")
    remaining = CONGRESO_TOTAL - CONGRESO_MIN_PROV * 50 - 2
    total = sum(provs.values())
    quota = Fraction(total, remaining)
    seats = {}
    fractions = {}
    for p, pop in provs.items():
        q = Fraction(pop) / quota
        seats[p] = CONGRESO_MIN_PROV + math.floor(q)
        fractions[p] = q - math.floor(q)
    left = CONGRESO_TOTAL - 2 - sum(seats.values())
    for p in sorted(fractions, key=lambda k: (-fractions[k], k))[:left]:
        seats[p] += 1
    seats[CEUTA] = 1
    seats[MELILLA] = 1
    return seats


def congreso_district(votes: dict[str, int], blank: int, seats: int, province: str) -> DhondtResult:
    """Escaños de una circunscripción del Congreso."""
    if province in (CEUTA, MELILLA):
        # art. 163.2: Ceuta y Melilla, candidato con más votos (sin barrera).
        winner = max(votes, key=lambda p: (votes[p], p)) if votes else None
        res = {p: 0 for p in votes}
        if winner:
            res[winner] = 1
        return DhondtResult(res, list(votes), Fraction(0), [])
    return dhondt(votes, seats, threshold=CONGRESO_THRESHOLD, blank_votes=blank)


# ───────────────────────── MUNICIPALES ─────────────────────────
MUNICIPAL_THRESHOLD = 0.05        # art. 180


def concejales_por_poblacion(poblacion: int) -> int:
    """Número de concejales según población de derecho (LOREG art. 179.1)."""
    escala = [(100, 3), (250, 5), (1000, 7), (2000, 9), (5000, 11),
              (10000, 13), (20000, 17), (50000, 21), (100000, 25)]
    for limite, n in escala:
        if poblacion <= limite:
            return n
    # > 100.000: un concejal más por cada 100.000 o fracción; +1 si sale par.
    n = 25 + math.ceil((poblacion - 100000) / 100000)
    return n + 1 if n % 2 == 0 else n


def regimen_municipal(poblacion: int) -> str:
    """Sistema aplicable (LOREG arts. 179–184)."""
    if poblacion < 100:
        return "concejo_abierto"           # art. 179.2 (salvo excepciones legales)
    if poblacion <= 250:
        return "listas_abiertas_mayoritario"  # art. 184
    return "dhondt_listas_cerradas"         # art. 180


def municipal(votes: dict[str, int], blank: int, poblacion: int) -> DhondtResult:
    regimen = regimen_municipal(poblacion)
    if regimen != "dhondt_listas_cerradas":
        raise ValueError(f"Municipio con régimen '{regimen}': no se asigna por D'Hondt")
    return dhondt(votes, concejales_por_poblacion(poblacion),
                  threshold=MUNICIPAL_THRESHOLD, blank_votes=blank)


# ───────────────────────── PARLAMENTO EUROPEO ─────────────────────────
def europeas(votes: dict[str, int], seats: int) -> DhondtResult:
    """Circunscripción única nacional, D'Hondt sin barrera (LOREG art. 214 y 216).

    Nota: la Decisión (UE, Euratom) 2018/994 prevé un umbral del 2–5 % para
    circunscripciones de más de 35 escaños cuando entre en vigor. Revisar antes
    de aplicar a convocatorias posteriores a 2024.
    """
    return dhondt(votes, seats, threshold=0.0)


# ───────────────────────── SENADO ─────────────────────────
SENADO_ESCANOS_PROVINCIA = 4      # art. 165.2 (provincias peninsulares)


def senado_provincia(votes_by_candidate: dict[str, int], seats: int = SENADO_ESCANOS_PROVINCIA) -> list[str]:
    """Voto limitado: cada elector marca hasta seats-1 (art. 166.1.a) y salen
    los `seats` candidatos INDIVIDUALES más votados (art. 166.1.b).

    Los votos son de candidatos, no de partidos: no se suman por candidatura.
    """
    ordered = sorted(votes_by_candidate, key=lambda c: (-votes_by_candidate[c], c))
    return ordered[:seats]
