"""Monta capturas del tablero en formatos de LinkedIn con marco Atlas.

Formatos: 1200×627 (enlace / horizontal), 1080×1080 (cuadrado), 1080×1350 (vertical 4:5).
Uso: python linkedin.py <carpeta_capturas> <recorte x0,y0,x1,y1> <carpeta_salida>
     cada captura: <nn>_<slug>.png ; el título sale de TITULOS.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from montar import LOGO, LUZ, MUTED, TINTA, VIOLETA, fuente

FORMATOS = {"1200x627": (1200, 627), "1080x1080": (1080, 1080), "1080x1350": (1080, 1350)}
TITULOS = {  # clave: parte final del nombre del archivo de captura
    "panel": ("Pronóstico generales 29-N", "52 circunscripciones · 350 escaños · 10.000 simulaciones"),
    "mapa": ("Mapa nacional", "Favorito 2026 por circunscripción · Canarias en recuadro"),
    "mapa_probabilidad": ("Probabilidad del favorito", "Cuánto de seguro es cada pronóstico"),
    "mapa_competitividad": ("Competitividad 2026", "Circunscripciones según probabilidad y margen"),
    "mapa_cambio": ("Cambio frente a 2023", "Dónde cambia la candidatura más votada"),
    "mapa_g2023": ("Más votada en 2023", "Punto de partida oficial"),
    "contiendas": ("52 contiendas", "Favorito, probabilidad, voto con intervalo, margen y escaños"),
    "c_28": ("Ficha: Madrid", "Voto y escaños por candidatura · escenarios"),
    "c_08": ("Ficha: Barcelona", "Voto y escaños por candidatura · escenarios"),
    "organizaciones": ("Candidaturas del BOE", "534 listas proclamadas, agrupadas por bloque"),
    "validacion": ("Validación del modelo", "Backtesting a ciegas 2015–2023"),
    "encuestas": ("Encuestas", "Media ponderada con enlace a cada publicación original"),
    "calidad": ("Data Quality Center", "Cada dato trazable a su fuente"),
    "metodologia": ("Metodología", "Modelo, incertidumbre, equivalencias y veda"),
    "p01_panel": ("Panel nacional", "Escaños esperados y mapa del favorito"),
    "p02_mapa": ("Mapa nacional", "10 métricas por circunscripción, dibujadas en DAX"),
    "p03_provincia": ("Mapa por provincia", "Municipios 2023 + pronóstico 2026"),
    "p04_circunscripciones": ("Circunscripciones", "Tabla de las 52 contiendas"),
    "p05_ficha": ("Ficha y escenarios", "Voto, escaños y escenarios por candidatura"),
    "p06_evolucion": ("Evolución 2015–2023", "La más votada en cinco generales"),
    "p07_encuestas": ("Encuestas", "Serie desde 2025 y encuestas usadas"),
    "p08_validacion": ("Validación del modelo", "Backtesting a ciegas con origen móvil"),
    "p09_datos": ("Datos y metodología", "Fuentes, controles y limitaciones"),
}
EYEBROW = {"web": "ATLAS ESPAÑA 29-N · PLATAFORMA WEB", "pbi": "ATLAS ESPAÑA 29-N · POWER BI"}
CANAL = "web"


def titulo_de(stem: str):
    for k in sorted(TITULOS, key=len, reverse=True):
        if stem.endswith(k):
            return TITULOS[k]
    return (stem.replace("_", " ").title(), "")


def _fondo(w, h):
    im = Image.new("RGB", (w, h), TINTA)
    d = ImageDraw.Draw(im)
    R = int(max(w, h) * 0.75)
    for r in range(R, 0, -6):  # resplandor violeta suave
        a = int(34 * (1 - r / R))
        d.ellipse([w * 0.65 - r, h * 0.55 - r, w * 0.65 + r, h * 0.55 + r], fill=(10 + a, 0, 36 + int(a * 2.2)))
    return im


def _envolver(d, texto, font, ancho):
    lineas, actual = [], ""
    for pal in texto.split():
        prueba = (actual + " " + pal).strip()
        if d.textlength(prueba, font=font) <= ancho:
            actual = prueba
        else:
            lineas.append(actual); actual = pal
    return lineas + [actual] if actual else lineas


def componer_horizontal(captura, titulo, sub, w, h):
    """1200×627: texto a la izquierda, captura grande a la derecha."""
    lienzo = _fondo(w, h)
    d = ImageDraw.Draw(lienzo)
    m = int(h * 0.07)
    col = int(w * 0.30)
    aw, ah = w - col - 2 * m, h - 2 * m
    k = min(aw / captura.width, ah / captura.height)
    cap = captura.resize((int(captura.width * k), int(captura.height * k)), Image.LANCZOS)
    x, y = w - m - cap.width, (h - cap.height) // 2
    mask = Image.new("L", cap.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cap.width - 1, cap.height - 1], radius=12, fill=255)
    d.rounded_rectangle([x - 3, y - 3, x + cap.width + 2, y + cap.height + 2], radius=14, fill=(90, 60, 150))
    lienzo.paste(cap, (x, y), mask)
    tw = x - 2 * m
    f_eb, f_ti, f_su = fuente(15, True), fuente(34, True), fuente(17)
    ty = m + 6
    for l in _envolver(d, EYEBROW[CANAL], f_eb, tw):
        d.text((m, ty), l, font=f_eb, fill=LUZ); ty += 22
    ty += 12
    for l in _envolver(d, titulo, f_ti, tw):
        d.text((m, ty), l, font=f_ti, fill=(242, 235, 250)); ty += 42
    ty += 6
    for l in _envolver(d, sub, f_su, tw):
        d.text((m, ty), l, font=f_su, fill=MUTED); ty += 24
    d.rectangle([m, ty + 10, m + 70, ty + 13], fill=VIOLETA)
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        lg = lg.resize((int(lg.width * 34 / lg.height), 34), Image.LANCZOS)
        lienzo.paste(lg, (m, h - m - 34 - 26), lg)
    d.text((m, h - m - 4), "atlas-espana-29n.vercel.app", font=fuente(13), fill=MUTED, anchor="ls")
    return lienzo


def componer(captura: Image.Image, titulo: str, sub: str, w: int, h: int) -> Image.Image:
    if w / h > 1.5:
        return componer_horizontal(captura, titulo, sub, w, h)
    lienzo = _fondo(w, h)
    d = ImageDraw.Draw(lienzo)
    m = int(w * 0.045)
    f_eb, f_ti, f_su = fuente(max(13, int(w * 0.014)), True), fuente(max(28, int(w * 0.036)), True), fuente(max(15, int(w * 0.017)))
    h_eb, h_ti, h_su = (d.textbbox((0, 0), t, font=f)[3] for t, f in (("A", f_eb), ("Áy", f_ti), ("Áy", f_su)))
    pie = max(46, int(h * 0.07))
    cab = h_eb + 10 + h_ti + 8 + h_su + 22  # alto real de la cabecera
    # captura escalada al área disponible
    aw, ah = w - 2 * m, h - cab - pie - 2 * m
    k = min(aw / captura.width, ah / captura.height)
    cap = captura.resize((int(captura.width * k), int(captura.height * k)), Image.LANCZOS)
    y0 = m + max(0, (ah - cap.height) // 2)  # el bloque cabecera + captura se centra en vertical
    y = y0
    d.text((m, y), EYEBROW[CANAL], font=f_eb, fill=LUZ); y += h_eb + 10
    d.text((m, y), titulo, font=f_ti, fill=(242, 235, 250)); y += h_ti + 8
    d.text((m, y), sub, font=f_su, fill=MUTED); y += h_su + 12
    d.rectangle([m, y, m + 80, y + 3], fill=VIOLETA); y += 10
    x = (w - cap.width) // 2
    mask = Image.new("L", cap.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cap.width - 1, cap.height - 1], radius=12, fill=255)
    d.rounded_rectangle([x - 3, y - 3, x + cap.width + 2, y + cap.height + 2], radius=14, fill=(90, 60, 150))
    lienzo.paste(cap, (x, y), mask)
    # pie: logo pequeño + web
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        lh = int(pie * 0.5)
        lg = lg.resize((int(lg.width * lh / lg.height), lh), Image.LANCZOS)
        lienzo.paste(lg, (m, h - pie + (pie - lh) // 2 - m // 3), lg)
    d.text((w - m, h - pie // 2 - m // 3), "atlas-espana-29n.vercel.app", font=fuente(max(13, int(w * 0.014))), fill=MUTED, anchor="rm")
    return lienzo


def lienzo_pbi(img: Image.Image):
    """Ubica el lienzo del informe (16:9) a partir de la barra de navegación oscura (#1D1631) del tablero."""
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(int)
    oscuro = (abs(a[..., 0] - 0x1D) < 12) & (abs(a[..., 1] - 0x16) < 12) & (abs(a[..., 2] - 0x31) < 14)
    col = oscuro[200:900].mean(axis=0)
    xs = np.flatnonzero(col > 0.6)
    x0, x1n = xs.min(), xs.max()
    fila = oscuro[:, x0 + 5]
    ys = np.flatnonzero(fila)
    y0 = ys.min()
    ancho = round((x1n - x0 + 1) * 1600 / 200)
    return (int(x0), int(y0), int(x0 + ancho), int(y0 + ancho * 9 / 16))


def main(entrada: Path, recorte: str, salida: Path, canal: str = "web"):
    global CANAL
    CANAL = canal
    for p in sorted(entrada.glob("*.png")):
        titulo, sub = titulo_de(p.stem)
        img = Image.open(p).convert("RGB")
        caja = lienzo_pbi(img) if recorte == "auto" else (0, 0, img.width, img.height) if recorte == "full" else tuple(map(int, recorte.split(",")))
        cap = img.crop(caja)
        (salida / "lienzo").mkdir(parents=True, exist_ok=True)
        cap.save(salida / "lienzo" / f"{p.stem}.png", optimize=True)
        for nombre, (w, h) in FORMATOS.items():
            o = salida / nombre / f"{p.stem}.png"
            o.parent.mkdir(parents=True, exist_ok=True)
            componer(cap, titulo, sub, w, h).save(o, optimize=True)
        print(p.stem)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "web")
