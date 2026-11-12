"""Video del tablero de Power BI a partir de capturas REALES (lienzos 1600×900) con movimiento de cámara.

Uso: python video_pbi.py <carpeta_lienzos> <carpeta_trabajo> <salida.mp4>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from montar import H, LUZ, MUTED, W, clip_imagen, fuente, placa

SEG, FUNDIDO, FPS = 5.6, 0.7, 30
# archivo, título, subtítulo, zoom final, centro (x, y) en el lienzo 1600×900
TOMAS = [  # archivo (lienzo), título, subtítulo, zoom final, centro (x, y) en el lienzo 1600×900
    ("01_p01_panel", "Panel nacional", "Probabilidades, escaños esperados y mapa del favorito", 1.5, (1080, 560)),
    ("02_p02_mapa", "Mapa nacional", "Favorito 2026 por circunscripción", 1.45, (1060, 470)),
    ("03_p02_mapa", "Mapa nacional", "Probabilidad del favorito", 1.45, (1060, 470)),
    ("04_p02_mapa", "Mapa nacional", "Competitividad 2026", 1.45, (1060, 470)),
    ("05_p02_mapa", "Mapa nacional", "Voto pronosticado de Vox", 1.45, (1060, 470)),
    ("06_p02_mapa", "Mapa nacional", "Cambio frente a 2023", 1.45, (1060, 470)),
    ("07_p03_provincia", "Mapa por provincia", "Madrid · municipios 2023 y pronóstico 2026", 1.5, (912, 490)),
    ("08_p03_provincia", "Mapa por provincia", "Barcelona · municipios 2023 y pronóstico 2026", 1.5, (912, 490)),
    ("09_p03_provincia", "Mapa por provincia", "Sevilla · municipios 2023 y pronóstico 2026", 1.5, (912, 490)),
    ("10_p04_circunscripciones", "Circunscripciones", "Las 52 contiendas, de la más ajustada a la más segura", 1.35, (700, 360)),
    ("11_p05_ficha", "Ficha y escenarios", "Sevilla · voto, escaños y escenarios", 1.45, (1066, 330)),
    ("12_p05_ficha", "Ficha y escenarios", "Bizkaia · voto, escaños y escenarios", 1.45, (1066, 330)),
    ("13_p06_evolucion", "Evolución 2015–2023", "La más votada en cinco generales", 1.25, (910, 200)),
    ("14_p07_encuestas", "Encuestas", "Serie publicada y encuestas usadas en la media", 1.3, (910, 300)),
    ("15_p08_validacion", "Validación del modelo", "Backtesting a ciegas con origen móvil", 1.4, (560, 210)),
    ("16_p09_datos", "Datos y metodología", "Cada dato trazable a su fuente", 1.3, (1256, 400)),
]


def rotulo(titulo, sub, ruta):
    """Tercio inferior transparente 1920×1080."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ft, fs = fuente(46, True), fuente(30)
    ancho = int(max(d.textlength(titulo, font=ft), d.textlength(sub, font=fs))) + 120
    d.rounded_rectangle([60, H - 210, 60 + ancho, H - 60], radius=18, fill=(10, 0, 36, 228))
    d.rectangle([60, H - 210, 68, H - 60], fill=(162, 30, 255, 255))
    d.text((100, H - 192), "ATLAS ESPAÑA 29-N · POWER BI", font=fuente(20, True), fill=LUZ)
    d.text((100, H - 160), titulo, font=ft, fill=(242, 235, 250))
    d.text((100, H - 106), sub, font=fs, fill=MUTED)
    im.save(ruta)


def toma(lienzo: Path, zf, centro, rot: Path, salida: Path):
    n = int(SEG * FPS)
    esc = 2  # se amplía el lienzo para que el zoom no pixele
    cx, cy = centro[0] * esc, centro[1] * esc
    p = f"(1-cos(PI*min(1,max(0,(on-24)/({n}-34)))))/2"  # 0,8 s quieto y luego zoom suave
    z = f"1+({zf}-1)*{p}"
    x = f"max(0,min(iw-iw/zoom,{p}*({cx}-iw/zoom/2)))"
    y = f"max(0,min(ih-ih/zoom,{p}*({cy}-ih/zoom/2)))"
    filtro = (f"[0]scale={1600 * esc}:{900 * esc}:flags=lanczos,zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS}[v];"
              f"[1]format=rgba,fade=t=in:st=0.5:d=0.5:alpha=1[r];[v][r]overlay=0:0,format=yuv420p")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", str(lienzo), "-loop", "1", "-i", str(rot),
                    "-filter_complex", filtro, "-t", f"{SEG}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    str(salida)], check=True)


def unir_fundidos(clips, duraciones, salida):
    args, filtro, prev, t = [], [], "0:v", 0.0
    for c in clips:
        args += ["-i", str(c)]
    for i in range(1, len(clips)):
        t += duraciones[i - 1] - FUNDIDO
        etiqueta = f"x{i}"
        filtro.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={FUNDIDO}:offset={t:.3f}[{etiqueta}]")
        prev = etiqueta
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args, "-filter_complex", ";".join(filtro), "-map", f"[{prev}]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(salida)],
                   check=True)


def main(lienzos: Path, trabajo: Path, salida: Path):
    trabajo.mkdir(parents=True, exist_ok=True)
    placa(trabajo / "intro.png", "ATLAS España 29-N", "Tablero de Power BI · generales 2026",
          ["Capturas reales de Power BI Desktop · 52 circunscripciones", "Mapas dibujados por DAX · modelo validado a ciegas 2015–2023"])
    placa(trabajo / "cierre.png", "Power BI · ATLAS España 29-N", "ATLAS Analytics · The intelligence behind every election",
          ["Plataforma web: atlas-espana-29n.vercel.app", "Fuentes: BOE · Ministerio del Interior · INE · encuestas publicadas"], eyebrow="TABLERO")
    clips, dur = [trabajo / "c00.mp4"], [4.5]
    clip_imagen(trabajo / "intro.png", 4.5, clips[0])
    for i, (archivo, titulo, sub, zf, centro) in enumerate(TOMAS, 1):
        rot = trabajo / f"r{i:02d}.png"
        rotulo(titulo, sub, rot)
        c = trabajo / f"c{i:02d}.mp4"
        toma(lienzos / f"{archivo}.png", zf, centro, rot, c)
        clips.append(c); dur.append(SEG)
        print("toma", i, archivo)
    c = trabajo / "c99.mp4"
    clip_imagen(trabajo / "cierre.png", 5, c)
    clips.append(c); dur.append(5)
    unir_fundidos(clips, dur, salida)
    print(salida)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
