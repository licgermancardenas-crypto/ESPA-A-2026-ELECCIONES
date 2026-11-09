"""Indicadores electorales con fórmula documentada.

Todas las funciones reciben votos/escaños por candidatura de UNA unidad
territorial y UNA convocatoria. Las comparaciones entre convocatorias
(volatilidad, swing) exigen un mapeo explícito de continuidad entre
candidaturas: ver gold.bridge_party_series. No se suman coaliciones a sus
partidos integrantes de forma automática.
"""

from __future__ import annotations

import math


def shares(votes: dict[str, int], denominator: int | None = None) -> dict[str, float]:
    """Proporción de voto. Por defecto sobre votos a candidaturas."""
    d = denominator if denominator is not None else sum(votes.values())
    return {p: (v / d if d else 0.0) for p, v in votes.items()}


def turnout(votantes: int, censo: int) -> float | None:
    """Participación = votantes / censo electoral (escrutinio)."""
    return votantes / censo if censo else None


def margin(votes: dict[str, int]) -> float | None:
    """Margen = (1º − 2º) / votos a candidaturas."""
    if len(votes) < 2:
        return None
    a, b = sorted(votes.values(), reverse=True)[:2]
    tot = sum(votes.values())
    return (a - b) / tot if tot else None


def competitiveness(votes: dict[str, int]) -> float | None:
    """Competitividad = 1 − margen (1 = empate técnico entre los dos primeros)."""
    m = margin(votes)
    return None if m is None else 1 - m


def effective_number_of_parties(values: dict[str, float]) -> float | None:
    """ENP de Laakso–Taagepera (1979): 1 / Σ pᵢ². Sirve para votos (ENEP) o escaños (ENPP)."""
    s = shares(values)
    h = sum(p * p for p in s.values())
    return 1 / h if h else None


def fragmentation_rae(values: dict[str, float]) -> float | None:
    """Fraccionalización de Rae (1967): 1 − Σ pᵢ²."""
    s = shares(values)
    if not s:
        return None
    return 1 - sum(p * p for p in s.values())


def dominance(votes: dict[str, int]) -> float | None:
    """Dominio = cuota del partido más votado."""
    s = shares(votes)
    return max(s.values()) if s else None


def gallagher(votes: dict[str, int], seats: dict[str, int]) -> float | None:
    """Índice de mínimos cuadrados de Gallagher (1991), en puntos porcentuales:
    sqrt(½ Σ (vᵢ − sᵢ)²) con v y s en %."""
    vt, st = sum(votes.values()), sum(seats.values())
    if not vt or not st:
        return None
    parties = set(votes) | set(seats)
    acc = sum((100 * votes.get(p, 0) / vt - 100 * seats.get(p, 0) / st) ** 2 for p in parties)
    return math.sqrt(acc / 2)


def seat_efficiency(votes: dict[str, int], seats: dict[str, int]) -> dict[str, float | None]:
    """Eficiencia = % escaños / % votos (1 = proporcional; >1 sobrerrepresentado)."""
    vs, ss = shares(votes), shares(seats)
    return {p: (ss.get(p, 0) / vs[p] if vs.get(p) else None) for p in votes}


def wasted_votes(votes: dict[str, int], seats: dict[str, int]) -> int:
    """Votos a candidaturas que no obtuvieron escaño en la circunscripción."""
    return sum(v for p, v in votes.items() if seats.get(p, 0) == 0)


def pedersen_volatility(prev: dict[str, float], curr: dict[str, float]) -> float:
    """Volatilidad de Pedersen (1979): ½ Σ |pᵢ,t − pᵢ,t−1|, en proporción [0,1].

    Las claves deben ser SERIES comparables (mismo partido o sucesor declarado),
    no siglas en bruto. Un partido que aparece/desaparece cuenta con 0 en el otro periodo.
    """
    a, b = shares(prev), shares(curr)
    keys = set(a) | set(b)
    return 0.5 * sum(abs(b.get(k, 0) - a.get(k, 0)) for k in keys)


def swing(prev_share: float, curr_share: float) -> float:
    """Swing simple de un partido = variación de su cuota (puntos sobre 1)."""
    return curr_share - prev_share


def butler_swing(prev: tuple[float, float], curr: tuple[float, float]) -> float:
    """Swing de Butler entre dos partidos A y B: ((A₂−A₁) − (B₂−B₁)) / 2."""
    return ((curr[0] - prev[0]) - (curr[1] - prev[1])) / 2
