"""Carrusel de hallazgos (1080×1350 + PDF) del pronóstico 29-N. Todas las cifras se calculan de los datos.

Uso: python carrusel.py web  <capturas_web_escritorio> <salida>
     python carrusel.py pbi  <lienzos_pbi>              <salida>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
from montar import LOGO, LUZ, MUTED, TINTA, VIOLETA, fuente  # noqa: E402

W, H = 1080, 1350
BLANCO, ROSA, ORO = (242, 235, 250), (255, 107, 154), (233, 182, 255)
M = 84
DATA = RAIZ / "web29n" / "data"
TOTAL = 8


def pct(v, d=0):
    return f"{v * 100:.{d}f}".replace(".", ",") + " %"


def num(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cifras():
    R = json.loads((DATA / "resumen.json").read_text(encoding="utf-8"))
    C = json.loads((DATA / "contiendas.json").read_text(encoding="utf-8"))
    B = json.loads((DATA / "backtest.json").read_text(encoding="utf-8"))
    from atlas_spain.pronostico import datos
    r23 = datos.resultados("02-202307").groupby("familia").escanos.sum()
    eq = {"PP": "PP", "PSOE": "PSOE", "Vox": "VOX", "ERC": "ERC", "Convergència / Junts": "JUNTS", "EH Bildu": "BILDU", "PNV": "PNV", "BNG": "BNG"}
    cambios = [c for c in C if not (eq.get(c["ganador_2023"]) == c["favorito"] or (c["favorito"] == "UPN_PP" and c["ganador_2023"] == "PP"))]
    sel = next(r for r in B["resumen"] if r["modelo"] == B["modelo_seleccionado"])
    pers = next(r for r in B["resumen"] if r["modelo"] == "persistencia")
    esc = {x["bloque"]: x for x in R["escanos"]}
    return {"R": R, "C": C, "B": B, "esc": esc, "r23": r23, "cambios": cambios, "sel": sel, "pers": pers,
            "ajustadas": sorted(C, key=lambda c: c["p_victoria_favorito"])[:6]}


def base(n):
    im = Image.new("RGB", (W, H), TINTA)
    d = ImageDraw.Draw(im)
    for r in range(1100, 0, -8):
        a = int(36 * (1 - r / 1100))
        d.ellipse([W * 0.75 - r, H * 0.35 - r, W * 0.75 + r, H * 0.35 + r], fill=(10 + a, 0, 36 + int(a * 2.2)))
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        lg = lg.resize((int(lg.width * 40 / lg.height), 40), Image.LANCZOS)
        im.paste(lg, (M, H - 92), lg)
    d.text((W - M, H - 72), f"{n}/{TOTAL}", font=fuente(24, True), fill=MUTED, anchor="rm")
    return im, d


def envolver(d, texto, font, ancho):
    out, cur = [], ""
    for p in texto.split():
        t = (cur + " " + p).strip()
        if d.textlength(t, font=font) <= ancho:
            cur = t
        else:
            out.append(cur)
            cur = p
    return out + ([cur] if cur else [])


def parrafo(d, xy, texto, font, color, ancho, interlineado=1.18):
    x, y = xy
    for l in envolver(d, texto, font, ancho):
        d.text((x, y), l, font=font, fill=color)
        y += font.size * interlineado
    return y


def cabecera(d, eyebrow, titulo, y=M, tam=56):
    d.text((M, y), eyebrow, font=fuente(22, True), fill=LUZ)
    y = parrafo(d, (M, y + 44), titulo, fuente(tam, True), BLANCO, W - 2 * M)
    d.rectangle([M, y + 14, M + 90, y + 18], fill=VIOLETA)
    return y + 40


def pegar(im, img, caja, radio=18):
    x0, y0, x1, y1 = (int(v) for v in caja)
    k = min((x1 - x0) / img.width, (y1 - y0) / img.height)
    img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
    x, y = x0 + (x1 - x0 - img.width) // 2, y0 + (y1 - y0 - img.height) // 2
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radio, fill=255)
    ImageDraw.Draw(im).rounded_rectangle([x - 3, y - 3, x + img.width + 2, y + img.height + 2], radius=radio + 2, fill=(90, 60, 150))
    im.paste(img, (x, y), mask)
    return y + img.height


def laminas(canal: str, caps: Path, X: dict):
    R, esc = X["R"], X["esc"]
    col = {k: hexrgb(v) for k, v in R["colores"].items()}
    L = []
    eyebrow = "ATLAS ESPAÑA 29-N · " + ("PLATAFORMA WEB" if canal == "web" else "POWER BI")
    # 1 portada
    im, d = base(1)
    d.text((M, 120), "ESPAÑA · GENERALES 29/11/2026", font=fuente(24, True), fill=LUZ)
    y = parrafo(d, (M, 175), "¿Quién gana el 29-N? Lo que dicen 10.000 simulaciones.", fuente(70, True), BLANCO, W - 2 * M, 1.12)
    d.text((M - 6, y + 40), pct(R["p_pp_primero"]), font=fuente(250, True), fill=ORO)
    y = parrafo(d, (M, y + 320), "de probabilidad de que el PP sea primero en escaños. "
                f"El PSOE, {pct(R['p_psoe_primero'])}.", fuente(36), BLANCO, W - 2 * M)
    parrafo(d, (M, y + 30), f"Media de {R['n_encuestas']} encuestas publicadas hasta el {R['corte']} · 52 circunscripciones.", fuente(28), MUTED, W - 2 * M)
    d.text((W - M, H - 150), "Desliza →", font=fuente(30, True), fill=LUZ, anchor="rm")
    L.append(im)
    # 2 escaños
    im, d = base(2)
    pp, ps, vx = esc["PP"], esc["PSOE"], esc["VOX"]
    y = cabecera(d, "ESCAÑOS ESPERADOS", f"PP {pp['media']:.0f}, PSOE {ps['media']:.0f}, Vox {vx['media']:.0f}")
    top = [x for x in R["escanos"] if x["media"] >= 0.5][:12]
    mx = max(x["p90"] for x in top) * 1.05
    fy = y + 20
    for x in top:
        d.text((M, fy + 6), R["cortos"].get(x["bloque"], x["bloque"]), font=fuente(26, True), fill=BLANCO)
        x0 = M + 200
        ancho = W - M - x0 - 120
        d.rounded_rectangle([x0, fy + 8, x0 + int(ancho * x["media"] / mx), fy + 38], radius=6, fill=col[x["bloque"]])
        d.line([x0 + int(ancho * x["p10"] / mx), fy + 23, x0 + int(ancho * x["p90"] / mx), fy + 23], fill=BLANCO, width=3)
        d.text((W - M, fy + 6), f"{x['media']:.0f}", font=fuente(28, True), fill=BLANCO, anchor="ra")
        fy += 66
    parrafo(d, (M, fy + 20), f"Barra: media. Línea: intervalo del 80 %. Mayoría absoluta PP + Vox: {pct(R['p_mayoria_pp_vox'])} de las simulaciones.",
            fuente(26), MUTED, W - 2 * M)
    L.append(im)
    # 3 mapa
    im, d = base(3)
    fav = R["favoritos"]
    y = cabecera(d, "MAPA DEL FAVORITO", f"El PP parte como favorito en {fav.get('PP', 0)} de las 52 circunscripciones")
    img = Image.open(caps / ("mapa.png" if canal == "web" else "02_p02_mapa.png")).convert("RGB")
    caja = (1150, 280, 1890, 1000) if canal == "web" else (int(img.width * 592 / 1600), int(img.height * 88 / 900), img.width, img.height)
    yb = pegar(im, img.crop(caja), (M, y + 10, W - M, H - 300))
    otros = ", ".join(f"{R['cortos'].get(b, b)} {n}" for b, n in fav.items() if b != "PP")
    parrafo(d, (M, yb + 30), f"Resto de favoritos: {otros}.", fuente(30), BLANCO, W - 2 * M)
    L.append(im)
    # 4 cambios
    im, d = base(4)
    ch = X["cambios"]
    y = cabecera(d, "QUÉ CAMBIA FRENTE A 2023", f"{len(ch)} circunscripciones cambiarían de candidatura más votada")
    for c in ch[:8]:
        d.ellipse([M, y + 22, M + 16, y + 38], fill=col[c["favorito"]])
        y = parrafo(d, (M + 34, y + 10), f"{c['provincia']}: de {c['ganador_2023']} a {R['nombres'][c['favorito']]} ({pct(c['p_victoria_favorito'])})",
                    fuente(32), BLANCO, W - 2 * M - 34) + 16
    y = parrafo(d, (M, y + 20), "Comparación por continuidad legal de cada formación. Sumar 2023 no tiene equivalente legal en 2026.", fuente(26), MUTED, W - 2 * M)
    mapa = RAIZ / "reports" / "mapas_29n" / "nacional_05_cambio.png"
    if mapa.exists():
        mi = Image.open(mapa).convert("RGB")
        pegar(im, mi.crop((0, int(mi.height * 0.1), mi.width, int(mi.height * 0.95))), (M, y + 20, W - M, H - 120))
    L.append(im)
    # 5 ajustadas
    im, d = base(5)
    y = cabecera(d, "FOTO FINISH", f"{R['muy_competitivas']} circunscripciones son muy competitivas")
    for c in X["ajustadas"]:
        p = c["p_victoria_favorito"]
        d.text((M, y + 14), c["provincia"], font=fuente(32, True), fill=BLANCO)
        d.text((W - M, y + 14), f"{R['cortos'].get(c['favorito'], c['favorito'])} {pct(p)}", font=fuente(30), fill=ORO, anchor="ra")
        d.rounded_rectangle([M, y + 62, W - M, y + 76], radius=7, fill=(40, 25, 80))
        d.rounded_rectangle([M, y + 62, M + int((W - 2 * M) * p), y + 76], radius=7, fill=col[c["favorito"]])
        y += 108
    parrafo(d, (M, y + 20), "Probabilidad de que el favorito sea la candidatura más votada en la circunscripción.", fuente(26), MUTED, W - 2 * M)
    L.append(im)
    # 6 la izquierda alternativa
    im, d = base(6)
    fa, sumar23 = esc.get("FA", {"media": 0, "p10": 0, "p90": 0}), int(X["r23"].get("Sumar", 0))
    pod = esc.get("PODEMOS", {"media": 0})
    y = cabecera(d, "EL ESPACIO A LA IZQUIERDA DEL PSOE", f"Sumar obtuvo {sumar23} escaños en 2023. Hoy, dividido.")
    filas = [("Frente Amplio", fa["media"], col["FA"]), ("Compromís", esc.get("COMPROMIS", {"media": 0})["media"], col["COMPROMIS"]),
             ("Podemos", pod["media"], col["PODEMOS"]), ("U. Pueblo Canario", esc.get("UPC", {"media": 0})["media"], col["UPC"])]
    yy = y + 40
    for nom, v, c in filas:
        d.text((M, yy), nom, font=fuente(32, True), fill=BLANCO)
        d.rounded_rectangle([M + 340, yy + 6, M + 340 + int(16 * v), yy + 36], radius=6, fill=c)
        d.text((M + 360 + int(16 * v), yy + 2), num(v), font=fuente(30, True), fill=BLANCO)
        yy += 80
    parrafo(d, (M, yy + 30), f"Escaños esperados 2026. Frente Amplio: {fa['p10']:.0f}–{fa['p90']:.0f} en el 80 % de las simulaciones. "
            "Son coaliciones nuevas: su implantación usa Sumar 2023 como sustituto geográfico, con más incertidumbre.", fuente(28), BLANCO, W - 2 * M)
    L.append(im)
    # 7 validación
    im, d = base(7)
    s, p = X["sel"], X["pers"]
    y = cabecera(d, "¿SE PUEDE PRONOSTICAR?", f"A ciegas, el modelo acertó la más votada en el {pct(s['acierto_ganador'])} de las circunscripciones")
    y = parrafo(d, (M, y + 6), f"Validado sobre 2015, 2016, abril y noviembre de 2019 y 2023, prediciendo cada elección solo con información previa. "
                f"Error medio: {num(s['mae_pp'])} puntos por candidatura; repetir el resultado anterior se equivoca {num(p['mae_pp'])}.",
                fuente(30), BLANCO, W - 2 * M)
    img = Image.open(caps / ("validacion.png" if canal == "web" else "08_p08_validacion.png")).convert("RGB")
    caja = (290, 150, 1890, 700) if canal == "web" else (int(img.width * 222 / 1600), int(img.height * 92 / 900), img.width, int(img.height * 494 / 900))
    pegar(im, img.crop(caja), (M, y + 30, W - M, H - 160))
    L.append(im)
    # 8 cierre
    im, d = base(8)
    y = cabecera(d, "29 DE NOVIEMBRE DE 2026", "Todo el detalle, circunscripción por circunscripción", tam=58)
    for t in (f"{R['contiendas']} circunscripciones y {R['escanos_total']} escaños, con escenarios.",
              "Candidaturas oficiales del BOE; resultados del Ministerio del Interior.",
              f"Encuestas hasta el {R['corte']}. Desde el {R['eleccion']['veda_desde']} rige la veda (art. 69.7 LOREG)."):
        d.ellipse([M, y + 22, M + 14, y + 36], fill=ORO)
        y = parrafo(d, (M + 34, y + 8), t, fuente(32), BLANCO, W - 2 * M - 34) + 18
    img = Image.open(caps / ("panel.png" if canal == "web" else "01_p01_panel.png")).convert("RGB")
    yb = pegar(im, img, (M, y + 30, W - M, H - 300))
    d.text((W // 2, yb + 70), "atlas-espana-29n.vercel.app", font=fuente(40, True), fill=ORO, anchor="ms")
    d.text((W // 2, yb + 116), eyebrow, font=fuente(24), fill=MUTED, anchor="ms")
    L.append(im)
    return L


def main(canal: str, caps: Path, salida: Path):
    from carrusel_vistas import a_pdf
    salida.mkdir(parents=True, exist_ok=True)
    ims = laminas(canal, caps, cifras())
    for i, im in enumerate(ims, 1):
        im.save(salida / f"hallazgos_{i:02d}.png", optimize=True)
    a_pdf(ims, salida / f"ATLAS_Espana_29N_{canal}_carrusel_hallazgos.pdf")
    print(salida, len(ims), "láminas")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
