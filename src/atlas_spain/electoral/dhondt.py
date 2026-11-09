"""Método D'Hondt con barrera legal y desempate según la LOREG.

LOREG art. 163.1:
  a) No se tienen en cuenta las candidaturas que no obtengan al menos el umbral
     (3 % Congreso; 5 % municipales) de los votos VÁLIDOS emitidos en la
     circunscripción. Votos válidos = votos a candidaturas + votos en blanco.
  c) Se divide el número de votos de cada candidatura por 1, 2, 3, ... hasta el
     número de escaños, y se asignan a los mayores cocientes.
  d) Empate de cocientes: el escaño va a la candidatura con mayor número total de
     votos. Si persiste el empate (mismo total), el primer empate se resuelve por
     sorteo y los siguientes de forma alternativa.

Este módulo no hace sorteos: si queda un empate total sin resolver lo informa
en `unresolved_ties` para que la decisión sea explícita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction


@dataclass
class DhondtResult:
    seats: dict[str, int]
    eligible: list[str]
    threshold_votes: Fraction
    quotients_used: list[tuple[str, Fraction]]
    unresolved_ties: list[list[str]] = field(default_factory=list)


def dhondt(votes: dict[str, int], seats: int, *, threshold: float = 0.0,
           blank_votes: int = 0, threshold_base: int | None = None) -> DhondtResult:
    """Asigna `seats` escaños.

    votes: votos por candidatura.
    threshold: proporción (0.03 = 3 %) sobre votos válidos (candidaturas + blancos),
               salvo que se pase `threshold_base` explícito (p. ej. otra base legal).
    """
    if seats < 0:
        raise ValueError("seats debe ser >= 0")
    if any(v < 0 for v in votes.values()):
        raise ValueError("votos negativos")
    base = threshold_base if threshold_base is not None else sum(votes.values()) + blank_votes
    # Fracciones exactas: evita errores de coma flotante en umbrales y cocientes.
    thr = Fraction(str(threshold)) * base
    eligible = [p for p, v in votes.items() if v > 0 and v >= thr]
    result = {p: 0 for p in votes}
    if not eligible or seats == 0:
        return DhondtResult(result, eligible, thr, [])

    quotients: list[tuple[Fraction, int, str]] = []
    for p in eligible:
        v = votes[p]
        for d in range(1, seats + 1):
            quotients.append((Fraction(v, d), v, p))
    # Orden: cociente desc, luego votos totales desc (desempate legal), luego nombre (estable)
    quotients.sort(key=lambda q: (-q[0], -q[1], q[2]))

    chosen = quotients[:seats]
    unresolved: list[list[str]] = []
    if len(quotients) > seats:
        last_q, last_v, _ = chosen[-1]
        nxt_q, nxt_v, _ = quotients[seats]
        if last_q == nxt_q and last_v == nxt_v:
            tied = sorted({p for q, v, p in quotients if q == last_q and v == last_v})
            unresolved.append(tied)

    for _, _, p in chosen:
        result[p] += 1
    return DhondtResult(result, eligible, thr, [(p, q) for q, _, p in chosen], unresolved)
