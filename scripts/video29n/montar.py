"""Monta videos a partir de cuadros con marca de tiempo (grabar_web.mjs) o capturas de pantalla.

Uso:
  python montar.py web <carpeta_trabajo> <salida.mp4>
  python montar.py powerbi <carpeta_trabajo> <salida.mp4>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
LOGO = RAIZ / "web29n" / "img" / "atlas_logo.png"
W, H = 1920, 1080
TINTA, VIOLETA, LUZ, MUTED = (10, 0, 36), (162, 30, 255), (233, 182, 255), (160, 143, 194)


def fuente(tam, negrita=False):
    for f in (("arialbd.ttf" if negrita else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def fondo():
    im = Image.new("RGB", (W, H), TINTA)
    d = ImageDraw.Draw(im)
    for r in range(900, 0, -6):  # resplandor violeta
        a = int(40 * (1 - r / 900))
        d.ellipse([W * 0.62 - r, H * 0.5 - r, W * 0.62 + r, H * 0.5 + r], fill=(10 + a, 0, 36 + int(a * 2.2)))
    return im


def placa(ruta, titulo, sub, lineas=(), eyebrow="ESPAÑA · GENERALES 29 NOV 2026"):
    im = fondo()
    d = ImageDraw.Draw(im)
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        lg = lg.resize((int(lg.width * 300 / lg.height * 0.25), 75))
        im.paste(lg, (140, 170), lg)
    d.text((140, 330), eyebrow, font=fuente(26, True), fill=LUZ)
    d.text((140, 380), titulo, font=fuente(96, True), fill=(242, 235, 250))
    d.text((140, 500), sub, font=fuente(40), fill=MUTED)
    for i, l in enumerate(lineas):
        d.text((140, 620 + i * 54), l, font=fuente(32), fill=(242, 235, 250) if i == 0 else MUTED)
    d.rectangle([140, 590, 260, 594], fill=VIOLETA)
    im.save(ruta)


def marco_movil(ruta_cuadro, ruta_salida, texto):
    im = fondo()
    d = ImageDraw.Draw(im)
    tel = Image.open(ruta_cuadro).convert("RGB")
    k = 940 / tel.height
    tel = tel.resize((int(tel.width * k), 940))
    x, y = W - 360 - tel.width // 2, 70
    d.rounded_rectangle([x - 16, y - 16, x + tel.width + 16, y + tel.height + 16], radius=46, fill=(30, 20, 60), outline=(90, 60, 150), width=3)
    im.paste(tel, (x, y))
    d.text((140, 380), "Versión móvil", font=fuente(80, True), fill=(242, 235, 250))
    d.text((140, 490), texto, font=fuente(36), fill=MUTED)
    im.save(ruta_salida, quality=92)


def ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def clip_imagen(img, seg, salida):
    ff("-loop", "1", "-t", str(seg), "-i", str(img), "-vf", f"scale={W}:{H},fade=t=in:st=0:d=0.6,fade=t=out:st={seg - 0.6}:d=0.6,format=yuv420p",
       "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(salida))


def clip_cuadros(carpeta: Path, salida, escala=f"{W}:{H}", transformar=None, max_dur=1.5):
    t = json.loads((carpeta / "tiempos.json").read_text())
    lista = carpeta / "lista.txt"
    with open(lista, "w", encoding="utf-8") as f:
        for i in range(len(t)):
            img = carpeta / f"f{i:05d}.jpg"
            if transformar:
                img = transformar(img)
            dur = min(max((t[i + 1] - t[i]) / 1000, 0.001), max_dur) if i + 1 < len(t) else 1.0
            f.write(f"file '{img.as_posix()}'\nduration {dur:.3f}\n")
        f.write(f"file '{img.as_posix()}'\n")
    ff("-f", "concat", "-safe", "0", "-i", str(lista), "-vf", f"scale={escala}:flags=lanczos,fps=30,format=yuv420p",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", str(salida))


def unir(partes, salida):
    lista = Path(salida).with_suffix(".txt")
    lista.write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in partes), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", "-movflags", "+faststart", str(salida))
    lista.unlink()


def web(trabajo: Path, salida):
    placa(trabajo / "intro.png", "ATLAS España 29-N", "Plataforma web de pronóstico · generales 2026",
          ["52 circunscripciones · 350 escaños · modelo validado a ciegas 2015–2023", "Mapa · tabla · fichas con escenarios · encuestas · validación"])
    placa(trabajo / "cierre.png", "atlas-espana-29n.vercel.app", "ATLAS Analytics · The intelligence behind every election",
          ["Fuentes: BOE (candidaturas) · Ministerio del Interior · INE", "Encuestas: vía Wikipedia, enlazadas a la original (pendientes de verificación)"],
          eyebrow="PLATAFORMA PÚBLICA")
    clip_imagen(trabajo / "intro.png", 4.5, trabajo / "p1.mp4")
    clip_cuadros(trabajo / "web", trabajo / "p2.mp4")
    mov = trabajo / "movil"
    (mov / "marco").mkdir(exist_ok=True)

    def enmarcar(img):
        o = mov / "marco" / img.name
        if not o.exists():
            marco_movil(img, o, "La misma plataforma, adaptada al móvil")
        return o
    clip_cuadros(mov, trabajo / "p3.mp4", transformar=enmarcar)
    clip_imagen(trabajo / "cierre.png", 5, trabajo / "p4.mp4")
    unir([trabajo / f"p{i}.mp4" for i in range(1, 5)], salida)


if __name__ == "__main__":
    modo, trabajo, salida = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    {"web": web}[modo](trabajo, salida)
    print(salida)
