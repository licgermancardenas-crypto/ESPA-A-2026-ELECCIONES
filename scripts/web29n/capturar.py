"""Capturas reales de la web 29-N (escritorio 1920x1080 y móvil 390x844) con Playwright + Edge.
Uso: python scripts/web29n/capturar.py [URL_BASE] [carpeta_salida]"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://127.0.0.1:8095/"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "reports/capturas/web")
VISTAS = ["panel", "mapa", "mapa?modo=probabilidad", "mapa?modo=competitividad", "mapa?modo=cambio", "mapa?modo=g2023",
          "contiendas", "c/28", "c/08", "organizaciones", "validacion", "encuestas", "calidad", "metodologia"]
DISP = {"escritorio": dict(viewport={"width": 1920, "height": 1080}, device_scale_factor=1),
        "movil": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)}

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    errores = []
    for nombre, kw in DISP.items():
        ctx = b.new_context(**kw)
        pg = ctx.new_page()
        pg.on("console", lambda m: errores.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
        for v in VISTAS:
            f = OUT / nombre / (v.replace("?modo=", "_").replace("/", "_") + ".png")
            if f.exists() and "--rehacer" not in sys.argv:
                continue
            pg.goto(BASE + "#" + v)
            pg.wait_for_timeout(3500 if "mapa" in v or v == "panel" else 1500)
            f.parent.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(f), timeout=120000, animations="disabled")
            # desbordamiento horizontal
            w = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            if w > 0:
                errores.append(f"{nombre} {v}: desborde horizontal {w}px")
        ctx.close()
    b.close()
print("\n".join(errores) or "sin errores")
