"""Fondo satelital para los mapas SVG de Power BI (ortofoto PNOA del IGN).

Los mapas de España del tablero se dibujan en un lienzo de 1000 px en UTM 30N
(EPSG:25830) con Canarias recolocada en un recuadro a escala 0,85. Este módulo
pide al servicio WMS del IGN la ortofoto con exactamente ese encuadre (y la de
Canarias aparte, que se pega en su recuadro), la comprime en JPEG y la guarda en
`fondo_satelite.csv` troceada en filas de menos de 32.000 caracteres (Power BI
corta los textos más largos). DAX la vuelve a unir y la pone debajo del mapa.

Fuente: PNOA © Instituto Geográfico Nacional, licencia CC BY 4.0.
"""

from __future__ import annotations

import base64
import io
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance

from atlas_spain import paths
from atlas_spain.http import fetch

SALIDA = paths.ROOT / "reports" / "powerbi" / "datos"
WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
PROY = 25830
ANCHO = 1000
ESC_CANARIAS = 0.85
TROZO = 30_000
ATRIBUCION = "Ortofoto PNOA © Instituto Geográfico Nacional (CC BY 4.0)"


def encuadre() -> dict:
    """Mismo cálculo que `powerbi_datos.geometria` (solo límites, sin disolver)."""
    fichero = next((paths.DATA / "gold" / "geo").glob("secciones_*.parquet"))
    g = gpd.read_parquet(fichero, columns=["CPRO", "CCA", "geometry"]).to_crs(PROY)
    pen = g[(g.CCA != "05") & (g.CPRO != "52")]
    can = g[g.CCA == "05"]
    px0, py0, px1, py1 = pen.total_bounds
    cx0, cy0, cx1, cy1 = can.total_bounds
    dx = (px0 + 20_000) - cx0
    dy = (py0 - 45_000) - (cy0 + (cy1 - cy0) * ESC_CANARIAS)
    # recuadro movido (escala desde (cx0, cy0) y traslado)
    mx0, my0 = cx0 + dx, cy0 + dy
    mx1, my1 = cx0 + (cx1 - cx0) * ESC_CANARIAS + dx, cy0 + (cy1 - cy0) * ESC_CANARIAS + dy
    caja = (mx0 - 15_000, my0 - 15_000, mx1 + 15_000, my1 + 15_000)
    x1 = max(px1, mx1, g[g.CPRO == "52"].total_bounds[2])
    y1 = max(py1, my1, g[g.CPRO == "52"].total_bounds[3])
    x0 = min(px0, mx0, g[g.CPRO == "52"].total_bounds[0], caja[0])
    y0 = min(py0, my0, g[g.CPRO == "52"].total_bounds[1], caja[1])
    k = ANCHO / (x1 - x0)
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "k": k, "alto": int(np.ceil((y1 - y0) * k)),
            "canarias_real": (cx0, cy0, cx1, cy1), "canarias_lienzo": (mx0, my0, mx1, my1), "caja": caja}


def _wms(bbox, ancho, alto) -> Image.Image:
    params = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": "OI.OrthoimageCoverage",
              "STYLES": "", "CRS": f"EPSG:{PROY}", "BBOX": ",".join(f"{v:.1f}" for v in bbox),
              "WIDTH": str(ancho), "HEIGHT": str(alto), "FORMAT": "image/jpeg"}
    url = WMS + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    r = fetch(url, timeout=120)
    img = Image.open(io.BytesIO(r.content))
    return img.convert("RGB")


def _wms_mosaico(bbox, ancho, alto, lado: int = 512) -> Image.Image:
    """El WMS corta las peticiones grandes: se pide en teselas de `lado` px y se unen."""
    x0, y0, x1, y1 = bbox
    sx, sy = (x1 - x0) / ancho, (y1 - y0) / alto  # metros por píxel
    out = Image.new("RGB", (ancho, alto))
    for py in range(0, alto, lado):
        for px in range(0, ancho, lado):
            w, h = min(lado, ancho - px), min(lado, alto - py)
            caja = (x0 + px * sx, y1 - (py + h) * sy, x0 + (px + w) * sx, y1 - py * sy)
            out.paste(_wms(caja, w, h), (px, py))
    return out


def imagen(escala: float = 1.6) -> tuple[Image.Image, dict]:
    """Ortofoto del lienzo completo (escala × 1000 px de ancho) con Canarias en su recuadro."""
    E = encuadre()
    W, H = int(ANCHO * escala), int(E["alto"] * escala)
    base = _wms_mosaico((E["x0"], E["y0"], E["x1"], E["y1"]), W, H)
    # Canarias: imagen real escalada a su tamaño en el lienzo y pegada en el recuadro
    cx0, cy0, cx1, cy1 = E["canarias_real"]
    bx0, by0, bx1, by1 = E["caja"]
    # el recuadro en coordenadas reales (deshaciendo escala y traslado)
    mx0, my0, _, _ = E["canarias_lienzo"]
    rx0 = cx0 + (bx0 - mx0) / ESC_CANARIAS
    ry0 = cy0 + (by0 - my0) / ESC_CANARIAS
    rx1 = cx0 + (bx1 - mx0) / ESC_CANARIAS
    ry1 = cy0 + (by1 - my0) / ESC_CANARIAS
    pw = int(round((bx1 - bx0) * E["k"] * escala))
    ph = int(round((by1 - by0) * E["k"] * escala))
    can = _wms_mosaico((rx0, ry0, rx1, ry1), pw, ph)
    px = int(round((bx0 - E["x0"]) * E["k"] * escala))
    py = int(round((E["y1"] - by1) * E["k"] * escala))
    base.paste(can, (px, py))
    # algo más de contraste y un leve oscurecido: los colores del mapa van encima
    fuera = np.asarray(base).min(axis=2) >= 245  # el WMS solo cubre España: fuera devuelve blanco
    base = ImageEnhance.Contrast(base).enhance(1.08)
    base = ImageEnhance.Brightness(base).enhance(0.92)
    arr = np.asarray(base).copy()
    arr[fuera] = 255
    return Image.fromarray(arr), E


def exportar(escala: float = 1.6, calidad: int = 72) -> dict:
    img, E = imagen(escala)
    SALIDA.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=calidad, optimize=True, progressive=True)
    img.save(SALIDA / "fondo_satelite.jpg", "JPEG", quality=calidad, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    trozos = [b64[i:i + TROZO] for i in range(0, len(b64), TROZO)]
    pd.DataFrame({"orden": range(1, len(trozos) + 1), "texto": trozos}).to_csv(
        SALIDA / "fondo_satelite.csv", index=False, encoding="utf-8")
    info = {"ancho_px": img.width, "alto_px": img.height, "alto_lienzo": E["alto"], "kb": round(len(b64) / 1024),
            "trozos": len(trozos), "fuente": ATRIBUCION}
    print(json.dumps(info, ensure_ascii=False))
    return info


if __name__ == "__main__":
    exportar()
