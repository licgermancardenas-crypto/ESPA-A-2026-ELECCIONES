"""Trazos SVG para los mapas del Power BI (DAX concatena los trazos precalculados).

Proyección: equirectangular con factor cos(40°) en x (España peninsular), Canarias trasladada a un recuadro.
Los anillos se codifican como trazos relativos con enteros (en medios píxeles) para que el texto pese poco.
"""
from __future__ import annotations

import numpy as np
from shapely.affinity import scale, translate

COS = float(np.cos(np.radians(40.0)))
DESPL = (5.8, 7.2)


def proyectar(geom, canarias: bool):
    g = translate(geom, *DESPL) if canarias else geom
    return scale(g, xfact=COS, yfact=1.0, origin=(0, 0))


def _anillos(geom):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    for p in polys:
        yield np.asarray(p.exterior.coords)
        for i in p.interiors:
            yield np.asarray(i.coords)


class Lienzo:
    """Transformación coordenadas proyectadas -> píxeles de un lienzo."""

    def __init__(self, bbox, ancho, x0=0, y0=0, alto=None):
        self.minx, self.miny, self.maxx, self.maxy = bbox
        self.k = ancho / (self.maxx - self.minx)
        if alto is not None:
            self.k = min(self.k, alto / (self.maxy - self.miny))
        self.x0, self.y0 = x0, y0
        self.ancho = round((self.maxx - self.minx) * self.k)
        self.alto = round((self.maxy - self.miny) * self.k)

    def xy(self, a):
        return np.column_stack([self.x0 + (a[:, 0] - self.minx) * self.k, self.y0 + (self.maxy - a[:, 1]) * self.k])


def trazo(geom, lz: Lienzo, tol_px: float = 0.6, escala: int = 2, area_min: float = 0.8) -> str:
    g = geom.simplify(tol_px / lz.k, preserve_topology=True)
    partes = []
    for ring in _anillos(g):
        p = np.round(lz.xy(ring) * escala).astype(int)
        d = np.diff(p, axis=0)
        d = d[(d != 0).any(axis=1)]
        if len(d) < 2:
            continue
        area = abs(np.cross(p[:-1], p[1:]).sum()) / 2 / escala ** 2
        if area < area_min:
            continue
        partes.append(f"M{p[0, 0]} {p[0, 1]}l" + " ".join(f"{a} {b}" for a, b in d[:-1]) + "z")
    return "".join(partes)


def centroide_px(geom, lz: Lienzo) -> tuple[int, int]:
    p = geom.representative_point()
    x, y = lz.xy(np.array([[p.x, p.y]]))[0]
    return int(round(x)), int(round(y))
