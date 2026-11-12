"""Carrusel de LinkedIn (1080×1350 + PDF): portada + una lámina por vista (captura REAL completa + zoom al detalle).

Uso: python carrusel_vistas.py web <carpeta_capturas_escritorio> <carpeta_salida>
     python carrusel_vistas.py pbi <carpeta_lienzos_pbi> <carpeta_salida>
Web: capturas 1920×1080 de reports/capturas/web/escritorio. Power BI: lienzos 1600×900 (linkedin.py, carpeta 'lienzo').
Las zonas de zoom están en coordenadas de la imagen de origen.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from carrusel import BLANCO, H, M, ORO, W, base, cabecera, parrafo, pegar
from montar import MUTED, fuente

VISTAS = {
    "web": {
        "ref": 1920, "portada": "mapa", "eyebrow": "ATLAS ESPAÑA 29-N · PLATAFORMA WEB",
        "titulo": "Así se ve un pronóstico electoral de las 52 circunscripciones",
        "sub": "Plataforma web pública · modo oscuro · adaptada al móvil · atlas-espana-29n.vercel.app",
        "laminas": [
            ("panel", "Panel nacional", "Probabilidades nacionales, escaños esperados con intervalo y mapa del favorito.", (290, 205, 1890, 980)),
            ("mapa", "Mapa electoral", "Siete modos: favorito, probabilidad, competitividad, voto por candidatura, cambio frente a 2023, ganador 2023 y calidad.", (1150, 280, 1890, 1000)),
            ("mapa_competitividad", "Competitividad", "Cada circunscripción clasificada por probabilidad del favorito y margen mediano.", (1150, 280, 1890, 1000)),
            ("contiendas", "Tabla de contiendas", "Las 52 circunscripciones, ordenables y filtrables, con voto e intervalo del 80 %.", (290, 150, 1890, 700)),
            ("c_28", "Ficha por circunscripción", "Voto, probabilidad de ser la más votada y escaños por candidatura, con escenarios. Aquí, Madrid.", (290, 230, 1890, 760)),
            ("validacion", "Validación", "Backtesting a ciegas 2015–2023 y calibración de la incertidumbre.", (290, 150, 1890, 700)),
            ("encuestas", "Encuestas", "Serie publicada con enlace a cada publicación original.", (290, 150, 1890, 760)),
            ("calidad", "Data Quality Center", "Fuentes, controles y limitaciones, a la vista.", (290, 150, 1890, 760)),
        ],
    },
    "pbi": {
        "ref": 1600, "portada": "02_p02_mapa", "eyebrow": "ATLAS ESPAÑA 29-N · POWER BI",
        "titulo": "Así se ve el pronóstico del 29-N en Power BI",
        "sub": "9 páginas · mapas dibujados en DAX · 52 circunscripciones y 8.132 municipios.",
        "laminas": [
            ("01_p01_panel", "Panel nacional", "Probabilidades nacionales, escaños esperados y mapa del favorito.", (222, 190, 1600, 894)),
            ("02_p02_mapa", "Mapa nacional", "Diez métricas por circunscripción, dibujadas con DAX y la cartografía del INE.", (592, 88, 1600, 894)),
            ("07_p03_provincia", "Mapa por provincia", "Municipios: más votada en 2023. Al lado, el pronóstico 2026 de la circunscripción.", (532, 88, 1600, 894)),
            ("10_p04_circunscripciones", "Circunscripciones", "Las 52 contiendas con favorito, probabilidad, intervalo, margen y escaños.", (222, 160, 1600, 600)),
            ("11_p05_ficha", "Ficha y escenarios", "Voto y escaños por candidatura, y qué pasa en cada escenario nacional.", (532, 92, 1600, 894)),
            ("13_p06_evolucion", "Evolución 2015–2023", "La candidatura más votada en cada circunscripción en cinco generales.", (222, 92, 1600, 312)),
            ("14_p07_encuestas", "Encuestas", "Serie de estimaciones y encuestas usadas en la media.", (222, 92, 1600, 512)),
            ("15_p08_validacion", "Validación", "Cinco modelos comparados a ciegas; se elige el más simple que no pierde precisión.", (222, 92, 1600, 494)),
        ],
    },
}


def lamina(n, total, img: Image.Image, cfg, titulo, texto, zona):
    im, d = base(n)
    d.text((W - M, H - 72), f"{n}/{total}", font=fuente(24, True), fill=MUTED, anchor="rm")
    y = cabecera(d, cfg["eyebrow"], titulo, tam=54)
    y = parrafo(d, (M, y + 4), texto, fuente(28), BLANCO, W - 2 * M) + 18
    k = img.width / cfg["ref"]
    zoom = img.crop(tuple(int(v * k) for v in zona))
    yb = pegar(im, img, (M, y, W - M, y + 500))
    d.text((M, yb + 26), "DETALLE", font=fuente(20, True), fill=ORO)
    pegar(im, zoom, (M, yb + 60, W - M, H - 120))
    return im


def portada(total, img, cfg):
    im, d = base(1)
    d.text((W - M, H - 72), f"1/{total}", font=fuente(24, True), fill=MUTED, anchor="rm")
    d.text((M, 120), "ESPAÑA · GENERALES 29/11/2026", font=fuente(24, True), fill=(233, 182, 255))
    y = parrafo(d, (M, 175), cfg["titulo"], fuente(64, True), BLANCO, W - 2 * M, 1.12)
    y = parrafo(d, (M, y + 24), cfg["sub"], fuente(30), MUTED, W - 2 * M)
    pegar(im, img, (M, y + 50, W - M, H - 200))
    d.text((W - M, H - 150), "Desliza →", font=fuente(30, True), fill=(233, 182, 255), anchor="rm")
    return im


def a_pdf(ims, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(ruta) as pdf:
        for im in ims:
            fig = plt.figure(figsize=(W / 150, H / 150), dpi=150)
            fig.figimage(np.asarray(im), 0, 0)
            pdf.savefig(fig, dpi=150)
            plt.close(fig)


def main(canal: str, entrada: Path, salida: Path):
    cfg = VISTAS[canal]
    salida.mkdir(parents=True, exist_ok=True)
    total = len(cfg["laminas"]) + 1
    ims = [portada(total, Image.open(entrada / f"{cfg['portada']}.png").convert("RGB"), cfg)]
    for i, (archivo, titulo, texto, zona) in enumerate(cfg["laminas"], 2):
        ims.append(lamina(i, total, Image.open(entrada / f"{archivo}.png").convert("RGB"), cfg, titulo, texto, zona))
    for i, im in enumerate(ims, 1):
        im.save(salida / f"carrusel_vistas_{i:02d}.png", optimize=True)
    a_pdf(ims, salida / f"ATLAS_Espana_29N_{canal}_carrusel_vistas.pdf")
    print(salida, len(ims), "láminas")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
