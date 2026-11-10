"""Función serverless de Vercel: el mismo motor estadístico de ATLAS SPAIN (atlas_spain.stats).

GET  /api/stats?metodo=catalogo
POST /api/stats   {"metodo": "...", "params": {...}}

El motor y el panel (data/gold/stat_panel.npz) se copian en web/_lib con
`python -m atlas_spain.web.estatico`. Solo depende de numpy y scipy.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LIB = Path(__file__).resolve().parent.parent / "_lib"
sys.path.insert(0, str(LIB))

from atlas_spain.stats.panel import Panel  # noqa: E402
from atlas_spain.stats.service import Servicio  # noqa: E402

SERVICIO = Servicio(Panel(LIB / "stat_panel.npz"))  # sin registro persistente: cada respuesta lleva su ejecución


class handler(BaseHTTPRequestHandler):
    def _responder(self, cuerpo: dict, codigo: int = 200):
        datos = json.dumps(cuerpo, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, s-maxage=86400" if codigo == 200 else "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        try:
            params = json.loads(q.get("params", ["{}"])[0])
        except json.JSONDecodeError:
            return self._responder({"error": "params no es JSON válido"}, 400)
        self._responder(SERVICIO.ejecutar(q.get("metodo", ["catalogo"])[0], params))

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > 200_000:
            return self._responder({"error": "petición demasiado grande"}, 413)
        try:
            pet = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._responder({"error": "cuerpo no es JSON válido"}, 400)
        self._responder(SERVICIO.ejecutar(pet.get("metodo", ""), pet.get("params") or {}))
